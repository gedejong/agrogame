"""Weather QA: validate, repair, and report for POWER/CSV/JSON inputs.

This module adds a *quality-assurance / audit* layer on top of the existing
weather repair primitives. It does **not** reimplement clamping or
interpolation: :func:`repair_weather_series` wraps
:func:`agrogame.weather.utils.sanitize_weather_series` and
:func:`agrogame.weather.utils.interpolate_weather_series` and diffs the series
before/after to produce an auditable trail of every change.

Run as a CLI::

    python -m agrogame.weather.qa <input.csv|json> [--repair] \
        [--format md|csv] [--out PATH]

Detected anomalies are also emitted as ``logging.WARNING`` records.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import logging
import sys
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, TextIO
from collections.abc import Sequence

from .types import WeatherRecord, WeatherSeries
from .utils import interpolate_weather_series, sanitize_weather_series

logger = logging.getLogger(__name__)

# POWER-style missing-data sentinel: any value at/below this is "missing".
SENTINEL_THRESHOLD = -900.0

# Float comparison tolerance when diffing pre/post repair values.
_DIFF_TOL = 1e-9

# Physically plausible ranges per numeric field (lo, hi); ``None`` = unbounded.
# Mirrors the clamps applied by ``sanitize_weather_series`` so validation and
# repair agree on what "out of range" means.
FIELD_RANGES: dict[str, tuple[float | None, float | None]] = {
    "tmin_c": (-60.0, 60.0),
    "tmax_c": (-60.0, 60.0),
    "relative_humidity_pct": (0.0, 100.0),
    "wind_m_s": (0.0, None),
    "shortwave_mj_m2": (0.0, None),
    "net_radiation_mj_m2": (0.0, None),
    "albedo": (0.0, 1.0),
    "precip_mm": (0.0, None),
}

# Fields interpolated (vs. constant-filled) by ``interpolate_weather_series``.
_CONTINUOUS_FIELDS = (
    "relative_humidity_pct",
    "wind_m_s",
    "shortwave_mj_m2",
    "net_radiation_mj_m2",
)

# Every numeric field, in report order.
_NUMERIC_FIELDS = tuple(FIELD_RANGES.keys())


class Severity(str, Enum):
    """Severity of a QA finding, ordered INFO < WARNING < ERROR."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class QAFinding:
    """A single anomaly detected in a weather series.

    ``day`` is ``None`` for series-level (aggregate) findings such as per-field
    missing counts. ``value`` carries the offending value or count when useful.
    """

    day: date | None
    field: str
    code: str
    severity: Severity
    message: str
    value: float | None = None


@dataclass(frozen=True)
class RepairAction:
    """A single change made to a weather series during repair.

    ``method`` is one of ``clamp`` / ``fill`` / ``interpolate`` / ``sentinel``.
    """

    day: date
    field: str
    old_value: float | None
    new_value: float | None
    method: str


@dataclass(frozen=True)
class QAReport:
    """Result of validating a weather series."""

    findings: tuple[QAFinding, ...]
    n_records: int

    def counts_by_severity(self) -> dict[Severity, int]:
        counts: dict[Severity, int] = dict.fromkeys(Severity, 0)
        for f in self.findings:
            counts[f.severity] += 1
        return counts

    def has_errors(self) -> bool:
        return any(f.severity is Severity.ERROR for f in self.findings)

    @property
    def n_anomalies(self) -> int:
        """Warnings + errors (INFO findings are not anomalies)."""
        return sum(1 for f in self.findings if f.severity is not Severity.INFO)


def _require_series(series: WeatherSeries) -> None:
    if not isinstance(series, WeatherSeries):
        raise ValueError(f"expected WeatherSeries, got {type(series).__name__}")
    if not isinstance(series.records, list):
        raise ValueError("WeatherSeries.records must be a list")


def _field_value(record: WeatherRecord, field: str) -> float | None:
    value = getattr(record, field)
    return None if value is None else float(value)


def _is_sentinel(value: float | None) -> bool:
    return value is not None and value <= SENTINEL_THRESHOLD


def _out_of_range(value: float, lo: float | None, hi: float | None) -> bool:
    if lo is not None and value < lo:
        return True
    if hi is not None and value > hi:
        return True
    return False


def validate_weather_series(series: WeatherSeries) -> QAReport:
    """Validate a weather series and return a :class:`QAReport`.

    Checks performed:

    - **Range** — each present numeric field against :data:`FIELD_RANGES`
      (``out_of_range``, warning).
    - **Sentinel** — present values ``<= -900`` (``sentinel``, error).
    - **Dates** — duplicate dates (``duplicate_date``, error), non-monotonic
      order (``non_monotonic``, error), and multi-day gaps (``date_gap``, info).
    - **Consistency** — ``tmin_c > tmax_c`` (``tmin_gt_tmax``, error).
    - **Missing** — per-field count of *gaps* (fields with some data but also
      missing values); ``missing``, info. Entirely-absent optional columns are
      not reported (they were simply not provided).
    """
    _require_series(series)
    records = series.records
    findings: list[QAFinding] = []

    # Per-record checks: sentinels, ranges, tmin/tmax consistency.
    for record in records:
        for field in _NUMERIC_FIELDS:
            value = _field_value(record, field)
            if value is None:
                continue
            if _is_sentinel(value):
                findings.append(
                    QAFinding(
                        day=record.day,
                        field=field,
                        code="sentinel",
                        severity=Severity.ERROR,
                        message=(
                            f"sentinel value {value:g} " f"(<= {SENTINEL_THRESHOLD:g})"
                        ),
                        value=value,
                    )
                )
                continue
            lo, hi = FIELD_RANGES[field]
            if _out_of_range(value, lo, hi):
                findings.append(
                    QAFinding(
                        day=record.day,
                        field=field,
                        code="out_of_range",
                        severity=Severity.WARNING,
                        message=f"value {value:g} outside [{lo}, {hi}]",
                        value=value,
                    )
                )
        if record.tmin_c > record.tmax_c:
            findings.append(
                QAFinding(
                    day=record.day,
                    field="tmin_c",
                    code="tmin_gt_tmax",
                    severity=Severity.ERROR,
                    message=f"tmin_c {record.tmin_c:g} > tmax_c {record.tmax_c:g}",
                    value=record.tmin_c,
                )
            )

    findings.extend(_date_findings(records))
    findings.extend(_missing_findings(records))
    return QAReport(findings=tuple(findings), n_records=len(records))


def _date_findings(records: Sequence[WeatherRecord]) -> list[QAFinding]:
    findings: list[QAFinding] = []
    seen: set[date] = set()
    prev: date | None = None
    for record in records:
        day = record.day
        if day in seen:
            findings.append(
                QAFinding(
                    day=day,
                    field="day",
                    code="duplicate_date",
                    severity=Severity.ERROR,
                    message=f"duplicate date {day.isoformat()}",
                )
            )
        seen.add(day)
        if prev is not None:
            if day < prev:
                findings.append(
                    QAFinding(
                        day=day,
                        field="day",
                        code="non_monotonic",
                        severity=Severity.ERROR,
                        message=(
                            f"date {day.isoformat()} precedes previous "
                            f"{prev.isoformat()}"
                        ),
                    )
                )
            elif (day - prev).days > 1:
                findings.append(
                    QAFinding(
                        day=day,
                        field="day",
                        code="date_gap",
                        severity=Severity.INFO,
                        message=(
                            f"{(day - prev).days - 1} day gap before "
                            f"{day.isoformat()}"
                        ),
                        value=float((day - prev).days - 1),
                    )
                )
        prev = day
    return findings


def _missing_findings(records: Sequence[WeatherRecord]) -> list[QAFinding]:
    findings: list[QAFinding] = []
    n = len(records)
    for field in _NUMERIC_FIELDS:
        missing = sum(1 for r in records if _field_value(r, field) is None)
        # Skip fully-present and entirely-absent columns; report only gaps.
        if missing == 0 or missing == n:
            continue
        findings.append(
            QAFinding(
                day=None,
                field=field,
                code="missing",
                severity=Severity.INFO,
                message=f"{missing} missing value(s)",
                value=float(missing),
            )
        )
    return findings


def _classify_method(field: str, old: float | None, new: float | None) -> str:
    """Categorise a pre/post field change into a repair method."""
    if _is_sentinel(old):
        return "sentinel"
    if old is None:
        if field in _CONTINUOUS_FIELDS:
            return "interpolate"
        return "fill"
    return "clamp"


def repair_weather_series(
    series: WeatherSeries,
) -> tuple[WeatherSeries, list[RepairAction]]:
    """Repair a weather series and return ``(repaired, audit_trail)``.

    Repair is performed by wrapping the existing primitives — sanitize first
    (sentinels to ``None``, range clamps, derived ``Rn``), then interpolate
    (fill gaps) — and diffing the result field-by-field against the input.

    The audit trail records only genuine repairs: present-but-invalid values
    (sentinel/clamp) and filled *gaps*. Entirely-absent optional columns that
    receive a default/derived value are not reported as repairs.

    Note: duplicate/non-monotonic dates and ``tmin_c > tmax_c`` are *not*
    repaired here (the underlying primitives do not reorder or swap); they are
    surfaced by :func:`validate_weather_series` instead.
    """
    _require_series(series)
    sanitized = sanitize_weather_series(series)
    repaired = interpolate_weather_series(sanitized)

    original = series.records
    fixed = repaired.records
    actions: list[RepairAction] = []

    # Precompute which columns are entirely absent in the input (not repairs).
    entirely_absent = {
        field: all(_field_value(r, field) is None for r in original)
        for field in _NUMERIC_FIELDS
    }

    for old_rec, new_rec in zip(original, fixed, strict=False):
        for field in _NUMERIC_FIELDS:
            old = _field_value(old_rec, field)
            new = _field_value(new_rec, field)
            if _values_equal(old, new):
                continue
            if old is None and entirely_absent[field]:
                # Default/derived fill of a column that was never provided.
                continue
            actions.append(
                RepairAction(
                    day=old_rec.day,
                    field=field,
                    old_value=old,
                    new_value=new,
                    method=_classify_method(field, old, new),
                )
            )
    return repaired, actions


def _values_equal(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= _DIFF_TOL


# --------------------------------------------------------------------------- #
# Raw loading (sentinel-preserving) — QA must see the true source data.
# --------------------------------------------------------------------------- #


def _raw_opt_float(value: str | float | None) -> float | None:
    """Parse an optional float, *preserving* sentinels (unlike the loader)."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid numeric weather value: {value!r}") from exc


def _record_from_mapping(row: dict[str, Any]) -> WeatherRecord:
    from .loader import _parse_date

    return WeatherRecord(
        day=_parse_date(str(row["date"])),
        tmin_c=float(row["tmin_c"]),
        tmax_c=float(row["tmax_c"]),
        relative_humidity_pct=_raw_opt_float(row.get("rh_pct")),
        wind_m_s=_raw_opt_float(row.get("wind_m_s")),
        shortwave_mj_m2=_raw_opt_float(row.get("rs_mj_m2")),
        net_radiation_mj_m2=_raw_opt_float(row.get("rn_mj_m2")),
        albedo=_raw_opt_float(row.get("albedo")),
        precip_mm=_raw_opt_float(row.get("precip_mm")),
    )


def load_raw_weather(path: Path) -> WeatherSeries:
    """Load a CSV/JSON weather file preserving sentinels for QA inspection."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", newline="") as handle:
            rows: list[dict[str, Any]] = list(csv.DictReader(handle))
    elif suffix == ".json":
        loaded = json.loads(path.read_text())
        if not isinstance(loaded, list):
            raise ValueError("JSON weather file must be a list of records")
        rows = loaded
    else:
        raise ValueError(f"unsupported weather file type: {path}")

    records: list[WeatherRecord] = []
    for i, row in enumerate(rows, start=1):
        try:
            records.append(_record_from_mapping(row))
        except (KeyError, ValueError) as exc:
            raise ValueError(f"weather parse error at record {i}: {exc}") from exc
    return WeatherSeries(records)


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #


def _fmt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def render_markdown(
    report: QAReport, actions: Sequence[RepairAction] | None = None
) -> str:
    counts = report.counts_by_severity()
    lines: list[str] = ["# Weather QA Report", ""]
    lines.append(f"- Records: {report.n_records}")
    lines.append(
        f"- Findings: {len(report.findings)} "
        f"(errors: {counts[Severity.ERROR]}, "
        f"warnings: {counts[Severity.WARNING]}, "
        f"info: {counts[Severity.INFO]})"
    )
    if actions is not None:
        lines.append(f"- Repairs: {len(actions)}")
    lines.append("")

    lines.append("## Findings")
    if report.findings:
        lines.append("| day | field | code | severity | value | message |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for f in report.findings:
            day = f.day.isoformat() if f.day is not None else ""
            lines.append(
                f"| {day} | {f.field} | {f.code} | {f.severity.value} "
                f"| {_fmt(f.value)} | {f.message} |"
            )
    else:
        lines.append("No anomalies detected.")
    lines.append("")

    if actions is not None:
        lines.append("## Repairs")
        if actions:
            lines.append("| day | field | old | new | method |")
            lines.append("| --- | --- | --- | --- | --- |")
            for a in actions:
                lines.append(
                    f"| {a.day.isoformat()} | {a.field} | {_fmt(a.old_value)} "
                    f"| {_fmt(a.new_value)} | {a.method} |"
                )
        else:
            lines.append("No repairs applied.")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_csv(report: QAReport, actions: Sequence[RepairAction] | None = None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "type",
            "day",
            "field",
            "code",
            "severity",
            "old_value",
            "new_value",
            "message",
        ]
    )
    for f in report.findings:
        writer.writerow(
            [
                "finding",
                f.day.isoformat() if f.day is not None else "",
                f.field,
                f.code,
                f.severity.value,
                _fmt(f.value),
                "",
                f.message,
            ]
        )
    for a in actions or ():
        writer.writerow(
            [
                "repair",
                a.day.isoformat(),
                a.field,
                a.method,
                "",
                _fmt(a.old_value),
                _fmt(a.new_value),
                "",
            ]
        )
    return buffer.getvalue()


def render_report(
    report: QAReport,
    fmt: str,
    actions: Sequence[RepairAction] | None = None,
) -> str:
    if fmt == "md":
        return render_markdown(report, actions)
    if fmt == "csv":
        return render_csv(report, actions)
    raise ValueError(f"unknown report format: {fmt!r}")


def log_anomalies(report: QAReport) -> None:
    """Emit each warning/error finding as a WARNING log record."""
    for f in report.findings:
        if f.severity is Severity.INFO:
            continue
        day = f.day.isoformat() if f.day is not None else "series"
        logger.warning(
            "weather QA [%s] %s/%s: %s", f.severity.value, day, f.field, f.message
        )


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m agrogame.weather.qa",
        description="Validate/repair and report on a weather CSV/JSON file.",
    )
    parser.add_argument("input", type=Path, help="weather CSV or JSON file")
    parser.add_argument(
        "--repair",
        action="store_true",
        help="run repair (sanitize + interpolate) and include an audit trail",
    )
    parser.add_argument(
        "--format",
        choices=["md", "csv"],
        default="md",
        help="report format (default: md)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="write report to PATH instead of stdout",
    )
    return parser


def main(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    """CLI entrypoint. Returns 0 when no error-severity findings, else 1."""
    args = _build_parser().parse_args(argv)
    out_stream = stdout if stdout is not None else sys.stdout

    series = load_raw_weather(args.input)
    report = validate_weather_series(series)
    log_anomalies(report)

    actions: list[RepairAction] | None = None
    if args.repair:
        _, actions = repair_weather_series(series)

    rendered = render_report(report, args.format, actions)
    if args.out is not None:
        args.out.write_text(rendered)
    else:
        out_stream.write(rendered)

    return 1 if report.has_errors() else 0


if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    sys.exit(main())
