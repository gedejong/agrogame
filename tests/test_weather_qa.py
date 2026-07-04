from __future__ import annotations

import io
import logging
from datetime import date

import pytest

from agrogame.weather.qa import (
    QAReport,
    RepairAction,
    Severity,
    load_raw_weather,
    main,
    render_csv,
    render_markdown,
    repair_weather_series,
    validate_weather_series,
)
from agrogame.weather.types import WeatherRecord, WeatherSeries


def _rec(
    day: date, tmin: float = 10.0, tmax: float = 20.0, **kw: float | None
) -> WeatherRecord:
    return WeatherRecord(day=day, tmin_c=tmin, tmax_c=tmax, **kw)


def _series(records: list[WeatherRecord]) -> WeatherSeries:
    return WeatherSeries(records)


def _codes(report: QAReport) -> list[str]:
    return [f.code for f in report.findings]


def _finding(report: QAReport, code: str):
    matches = [f for f in report.findings if f.code == code]
    assert matches, f"expected a {code!r} finding, got {_codes(report)}"
    return matches[0]


# --------------------------------------------------------------------------- #
# Validation: one test per anomaly class
# --------------------------------------------------------------------------- #


def test_out_of_range_relative_humidity() -> None:
    d = date(2024, 6, 1)
    report = validate_weather_series(_series([_rec(d, relative_humidity_pct=150.0)]))
    f = _finding(report, "out_of_range")
    assert f.field == "relative_humidity_pct"
    assert f.severity is Severity.WARNING
    assert f.value == 150.0
    assert f.day == d


def test_sentinel_detected_as_error() -> None:
    d = date(2024, 6, 1)
    report = validate_weather_series(_series([_rec(d, relative_humidity_pct=-999.0)]))
    f = _finding(report, "sentinel")
    assert f.field == "relative_humidity_pct"
    assert f.severity is Severity.ERROR
    # A sentinel must not also be reported as out-of-range.
    assert "out_of_range" not in _codes(report)


def test_sentinel_in_required_temperature_field() -> None:
    d = date(2024, 6, 1)
    report = validate_weather_series(_series([_rec(d, tmin=-999.0, tmax=20.0)]))
    f = _finding(report, "sentinel")
    assert f.field == "tmin_c"
    assert f.severity is Severity.ERROR


def test_duplicate_date() -> None:
    d = date(2024, 6, 1)
    report = validate_weather_series(_series([_rec(d), _rec(d)]))
    f = _finding(report, "duplicate_date")
    assert f.field == "day"
    assert f.severity is Severity.ERROR


def test_non_monotonic_date() -> None:
    report = validate_weather_series(
        _series([_rec(date(2024, 6, 2)), _rec(date(2024, 6, 1))])
    )
    f = _finding(report, "non_monotonic")
    assert f.severity is Severity.ERROR
    assert f.day == date(2024, 6, 1)


def test_date_gap_is_info() -> None:
    report = validate_weather_series(
        _series([_rec(date(2024, 6, 1)), _rec(date(2024, 6, 4))])
    )
    f = _finding(report, "date_gap")
    assert f.severity is Severity.INFO
    assert f.value == 2.0  # two missing days between 06-01 and 06-04


def test_tmin_gt_tmax_consistency() -> None:
    d = date(2024, 6, 1)
    report = validate_weather_series(_series([_rec(d, tmin=25.0, tmax=20.0)]))
    f = _finding(report, "tmin_gt_tmax")
    assert f.field == "tmin_c"
    assert f.severity is Severity.ERROR


def test_missing_counts_only_reports_gaps() -> None:
    days = [date(2024, 6, i) for i in (1, 2, 3)]
    records = [
        _rec(days[0], wind_m_s=2.0),
        _rec(days[1], wind_m_s=None),  # gap
        _rec(days[2], wind_m_s=3.0),
    ]
    report = validate_weather_series(_series(records))
    f = _finding(report, "missing")
    assert f.field == "wind_m_s"
    assert f.day is None  # aggregate finding
    assert f.value == 1.0
    assert f.severity is Severity.INFO


def test_entirely_absent_column_not_reported_as_missing() -> None:
    # precip_mm and net_radiation are absent from every record: not "gaps".
    days = [date(2024, 6, i) for i in (1, 2)]
    records = [_rec(days[0]), _rec(days[1])]
    report = validate_weather_series(_series(records))
    assert "missing" not in _codes(report)


def test_clean_series_has_no_findings() -> None:
    days = [date(2024, 6, i) for i in (1, 2, 3)]
    records = [
        WeatherRecord(
            day=d,
            tmin_c=10.0,
            tmax_c=20.0,
            relative_humidity_pct=60.0,
            wind_m_s=2.5,
            shortwave_mj_m2=18.0,
            net_radiation_mj_m2=12.0,
            albedo=0.23,
            precip_mm=1.0,
        )
        for d in days
    ]
    report = validate_weather_series(_series(records))
    assert report.findings == ()
    assert not report.has_errors()
    assert report.n_anomalies == 0


def test_validate_rejects_non_series() -> None:
    with pytest.raises(ValueError):
        validate_weather_series([_rec(date(2024, 6, 1))])  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Repair: audit trail correctness
# --------------------------------------------------------------------------- #


def test_repair_clamp_action() -> None:
    d = date(2024, 6, 1)
    repaired, actions = repair_weather_series(
        _series([_rec(d, relative_humidity_pct=150.0)])
    )
    assert repaired.records[0].relative_humidity_pct == 100.0
    clamp = [a for a in actions if a.method == "clamp"]
    assert clamp == [
        RepairAction(
            day=d,
            field="relative_humidity_pct",
            old_value=150.0,
            new_value=100.0,
            method="clamp",
        )
    ]


def test_repair_interpolate_action() -> None:
    days = [date(2024, 6, i) for i in (1, 2, 3)]
    records = [
        _rec(days[0], relative_humidity_pct=50.0),
        _rec(days[1], relative_humidity_pct=None),
        _rec(days[2], relative_humidity_pct=70.0),
    ]
    repaired, actions = repair_weather_series(_series(records))
    assert repaired.records[1].relative_humidity_pct == pytest.approx(60.0)
    interp = [a for a in actions if a.method == "interpolate"]
    assert len(interp) == 1
    assert interp[0].day == days[1]
    assert interp[0].old_value is None
    assert interp[0].new_value == pytest.approx(60.0)


def test_repair_fill_action_precip() -> None:
    days = [date(2024, 6, i) for i in (1, 2, 3)]
    records = [
        _rec(days[0], precip_mm=5.0),
        _rec(days[1], precip_mm=None),  # gap -> constant fill 0
        _rec(days[2], precip_mm=3.0),
    ]
    _, actions = repair_weather_series(_series(records))
    fill = [a for a in actions if a.field == "precip_mm"]
    assert fill == [
        RepairAction(
            day=days[1],
            field="precip_mm",
            old_value=None,
            new_value=0.0,
            method="fill",
        )
    ]


def test_repair_sentinel_action() -> None:
    days = [date(2024, 6, i) for i in (1, 2, 3)]
    records = [
        _rec(days[0], relative_humidity_pct=50.0),
        _rec(days[1], relative_humidity_pct=-999.0),  # sentinel -> cleaned + filled
        _rec(days[2], relative_humidity_pct=70.0),
    ]
    repaired, actions = repair_weather_series(_series(records))
    assert repaired.records[1].relative_humidity_pct == pytest.approx(60.0)
    sentinel = [a for a in actions if a.method == "sentinel"]
    assert len(sentinel) == 1
    assert sentinel[0].old_value == -999.0
    assert sentinel[0].new_value == pytest.approx(60.0)


def test_repair_clean_series_empty_audit_trail() -> None:
    days = [date(2024, 6, i) for i in (1, 2, 3)]
    records = [
        WeatherRecord(
            day=d,
            tmin_c=10.0,
            tmax_c=20.0,
            relative_humidity_pct=60.0,
            wind_m_s=2.5,
            shortwave_mj_m2=18.0,
            net_radiation_mj_m2=12.0,
            albedo=0.23,
            precip_mm=1.0,
        )
        for d in days
    ]
    _, actions = repair_weather_series(_series(records))
    assert actions == []


def test_repair_absent_column_not_audited() -> None:
    # rn/precip absent everywhere: sanitize derives/defaults them, but that is
    # not a repair of provided data, so no audit entries for those fields.
    days = [date(2024, 6, i) for i in (1, 2)]
    records = [
        _rec(days[0], shortwave_mj_m2=18.0, albedo=0.23),
        _rec(days[1], shortwave_mj_m2=20.0, albedo=0.23),
    ]
    _, actions = repair_weather_series(_series(records))
    assert actions == []


def test_repair_does_not_mutate_input() -> None:
    d = date(2024, 6, 1)
    original = _rec(d, relative_humidity_pct=150.0)
    series = _series([original])
    repair_weather_series(series)
    assert series.records[0].relative_humidity_pct == 150.0


# --------------------------------------------------------------------------- #
# Raw loading (sentinel-preserving)
# --------------------------------------------------------------------------- #


def _write_csv(path, rows: list[str]) -> None:
    header = "date,tmin_c,tmax_c,rh_pct,wind_m_s,rs_mj_m2,precip_mm,albedo"
    path.write_text("\n".join([header, *rows]) + "\n")


def test_load_raw_preserves_sentinel(tmp_path) -> None:
    csv_path = tmp_path / "w.csv"
    _write_csv(csv_path, ["2024-06-01,10,22,-999,2.5,18,1,0.23"])
    series = load_raw_weather(csv_path)
    # The canonical loader would strip -999 to None; the raw loader keeps it.
    assert series.records[0].relative_humidity_pct == -999.0


def test_load_raw_json(tmp_path) -> None:
    json_path = tmp_path / "w.json"
    json_path.write_text(
        '[{"date": "2024-06-01", "tmin_c": 10, "tmax_c": 22, "rh_pct": 60}]'
    )
    series = load_raw_weather(json_path)
    assert series.records[0].relative_humidity_pct == 60.0


def test_load_raw_rejects_unknown_suffix(tmp_path) -> None:
    bad = tmp_path / "w.txt"
    bad.write_text("nope")
    with pytest.raises(ValueError):
        load_raw_weather(bad)


def test_load_raw_reports_bad_row(tmp_path) -> None:
    csv_path = tmp_path / "w.csv"
    _write_csv(csv_path, ["2024-06-01,not_a_number,22,60,2.5,18,1,0.23"])
    with pytest.raises(ValueError, match="record 1"):
        load_raw_weather(csv_path)


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #


def _bad_report() -> QAReport:
    return validate_weather_series(
        _series(
            [_rec(date(2024, 6, 1), tmin=25.0, tmax=20.0, relative_humidity_pct=150.0)]
        )
    )


def test_render_markdown_lists_findings() -> None:
    md = render_markdown(_bad_report())
    assert "# Weather QA Report" in md
    assert "tmin_gt_tmax" in md
    assert "out_of_range" in md
    assert "## Findings" in md


def test_render_markdown_no_findings() -> None:
    report = validate_weather_series(_series([_rec(date(2024, 6, 1))]))
    md = render_markdown(report)
    assert "No anomalies detected." in md


def test_render_markdown_includes_repairs_section() -> None:
    d = date(2024, 6, 1)
    series = _series([_rec(d, relative_humidity_pct=150.0)])
    report = validate_weather_series(series)
    _, actions = repair_weather_series(series)
    md = render_markdown(report, actions)
    assert "## Repairs" in md
    assert "clamp" in md


def test_render_csv_has_finding_and_repair_rows() -> None:
    d = date(2024, 6, 1)
    series = _series([_rec(d, relative_humidity_pct=150.0)])
    report = validate_weather_series(series)
    _, actions = repair_weather_series(series)
    out = render_csv(report, actions)
    lines = out.strip().splitlines()
    assert lines[0].startswith(
        "type,day,field,code,severity,old_value,new_value,message"
    )
    assert any(line.startswith("finding,") for line in lines)
    assert any(line.startswith("repair,") for line in lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _seeded_csv(path) -> None:
    _write_csv(
        path,
        [
            "2024-06-01,10,22,60,2.5,18,1,0.23",  # clean
            "2024-06-02,25,20,55,3.0,20,0,0.23",  # tmin>tmax
            "2024-06-03,12,25,150,,21,2,0.23",  # rh out-of-range, wind missing
            "2024-06-04,12,25,-999,3,21,2,0.23",  # rh sentinel
            "2024-06-04,12,25,50,3,21,2,0.23",  # duplicate date
            "2024-06-01,12,25,50,3,21,2,0.23",  # non-monotonic
        ],
    )


def test_cli_markdown_to_stdout_returns_error_code(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    _seeded_csv(csv_path)
    buf = io.StringIO()
    rc = main([str(csv_path)], stdout=buf)
    out = buf.getvalue()
    assert rc == 1  # error-severity findings present
    for code in (
        "tmin_gt_tmax",
        "out_of_range",
        "sentinel",
        "duplicate_date",
        "non_monotonic",
    ):
        assert code in out


def test_cli_csv_format(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    _seeded_csv(csv_path)
    buf = io.StringIO()
    main([str(csv_path), "--format", "csv"], stdout=buf)
    assert buf.getvalue().startswith("type,day,field,code")


def test_cli_repair_writes_audit_to_out(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    _seeded_csv(csv_path)
    out_path = tmp_path / "report.md"
    rc = main([str(csv_path), "--repair", "--out", str(out_path)], stdout=io.StringIO())
    assert rc == 1
    text = out_path.read_text()
    assert "## Repairs" in text
    assert "clamp" in text  # rh 150 -> 100
    assert "sentinel" in text  # rh -999 cleaned
    # Input file is not modified by QA.
    assert "150" in csv_path.read_text()


def test_cli_clean_file_exit_zero(tmp_path) -> None:
    csv_path = tmp_path / "clean.csv"
    _write_csv(
        csv_path,
        [
            "2024-06-01,10,22,60,2.5,18,1,0.23",
            "2024-06-02,11,24,55,3.0,20,0,0.23",
        ],
    )
    buf = io.StringIO()
    rc = main([str(csv_path)], stdout=buf)
    assert rc == 0
    assert "No anomalies detected." in buf.getvalue()


def test_cli_emits_warning_logs(tmp_path, caplog) -> None:
    csv_path = tmp_path / "bad.csv"
    _seeded_csv(csv_path)
    with caplog.at_level(logging.WARNING, logger="agrogame.weather.qa"):
        main([str(csv_path)], stdout=io.StringIO())
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "weather QA" in messages
    assert "tmin_gt_tmax" in messages or "tmin_c" in messages


# --------------------------------------------------------------------------- #
# Plot-script integration flag (add_weather_args / get_weather_series)
# --------------------------------------------------------------------------- #


def test_cli_flag_warn_only_does_not_mutate(tmp_path, caplog) -> None:
    from argparse import ArgumentParser

    from agrogame.weather.cli import add_weather_args, get_weather_series

    csv_path = tmp_path / "bad.csv"
    _seeded_csv(csv_path)
    parser = ArgumentParser()
    add_weather_args(parser)
    args = parser.parse_args(["--weather-file", str(csv_path), "--weather-qa"])
    with caplog.at_level(logging.WARNING, logger="agrogame.weather.qa"):
        series = get_weather_series(args, days=10)
    assert series is not None
    # Warn-only: series unchanged (rh 150 still present, not clamped).
    assert any(r.relative_humidity_pct == 150.0 for r in series.records)
    assert "weather QA" in " ".join(r.getMessage() for r in caplog.records)


def test_cli_flag_repair_mutates(tmp_path) -> None:
    from argparse import ArgumentParser

    from agrogame.weather.cli import add_weather_args, get_weather_series

    csv_path = tmp_path / "bad.csv"
    _seeded_csv(csv_path)
    parser = ArgumentParser()
    add_weather_args(parser)
    args = parser.parse_args(["--weather-file", str(csv_path), "--weather-qa-repair"])
    series = get_weather_series(args, days=10)
    assert series is not None
    # Repaired: no rh value exceeds 100.
    assert all(
        r.relative_humidity_pct is None or r.relative_humidity_pct <= 100.0
        for r in series.records
    )
