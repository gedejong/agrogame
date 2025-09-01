from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import urllib.request
from urllib.error import HTTPError, URLError
from .constants import DEFAULT_ALBEDO, POWER_DAILY_PARAMS_MINIMAL

from .types import WeatherRecord, WeatherSeries
from agrogame.config.validation import validate_data


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {s}")


def load_weather(path: Path) -> WeatherSeries:
    if path.suffix.lower() == ".csv":
        return _load_csv(path)
    if path.suffix.lower() == ".json":
        return _load_json(path)
    raise ValueError(f"Unsupported weather file type: {path}")


def _load_csv(path: Path) -> WeatherSeries:
    rows: List[WeatherRecord] = []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader, start=2):
            try:
                rows.append(
                    WeatherRecord(
                        day=_parse_date(r["date"]),
                        tmin_c=float(r["tmin_c"]),
                        tmax_c=float(r["tmax_c"]),
                        relative_humidity_pct=_opt_float(r.get("rh_pct")),
                        wind_m_s=_opt_float(r.get("wind_m_s")),
                        shortwave_mj_m2=_opt_float(r.get("rs_mj_m2")),
                        net_radiation_mj_m2=_opt_float(r.get("rn_mj_m2")),
                        albedo=_opt_float(r.get("albedo")),
                        precip_mm=_opt_float(r.get("precip_mm")),
                    )
                )
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"CSV parse error at line {i}: {e}") from e
    return WeatherSeries(rows)


def _load_json(path: Path) -> WeatherSeries:
    data = json.loads(path.read_text())
    # Validate JSON weather structure when available
    try:
        validate_data(data, "weather")
    except Exception:
        # Be permissive: keep legacy support if schema not matched
        pass
    rows: List[WeatherRecord] = []
    for i, r in enumerate(data, start=1):
        try:
            rows.append(
                WeatherRecord(
                    day=_parse_date(r["date"]),
                    tmin_c=float(r["tmin_c"]),
                    tmax_c=float(r["tmax_c"]),
                    relative_humidity_pct=_opt_float(r.get("rh_pct")),
                    wind_m_s=_opt_float(r.get("wind_m_s")),
                    shortwave_mj_m2=_opt_float(r.get("rs_mj_m2")),
                    net_radiation_mj_m2=_opt_float(r.get("rn_mj_m2")),
                    albedo=_opt_float(r.get("albedo")),
                    precip_mm=_opt_float(r.get("precip_mm")),
                )
            )
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"JSON parse error at index {i}: {e}") from e
    return WeatherSeries(rows)


def _opt_float(v: Optional[str | float]) -> Optional[float]:
    """Parse optional float from CSV/JSON, treating sentinel -999 as missing."""
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except Exception:  # noqa: BLE001
        return None
    # NASA POWER uses -999 or -99 for missing
    if f <= -900.0:
        return None
    return f


def load_weather_auto(
    latitude: float, longitude: float, start: date, end: date
) -> WeatherSeries:
    """Fetch daily weather from NASA POWER automatically.

    Minimal, dependency-free client.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start": start.strftime("%Y%m%d"),
        "end": end.strftime("%Y%m%d"),
        "community": "AG",
        # POWER recommended dailies; use WS10M/WS2M may vary by dataset; prefer WS10M
        # Keep request minimal to avoid 422s
        "parameters": (POWER_DAILY_PARAMS_MINIMAL),
        "format": "JSON",
    }
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters={params['parameters']}"
        f"&community=AG&longitude={longitude}&latitude={latitude}"
        f"&start={params['start']}&end={params['end']}&format=JSON"
    )
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:  # nosec B310
            payload = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError) as e:  # noqa: PERF203
        raise ValueError(f"NASA POWER request failed: {e}") from e

    d = payload["properties"]["parameter"]
    days = sorted(int(k) for k in d["T2M_MAX"].keys())
    records: List[WeatherRecord] = []

    def _clean(value: Optional[float]) -> Optional[float]:
        if value is None:
            return None
        # Convert POWER sentinel to None
        if value <= -900.0:
            return None
        return float(value)

    for k in days:
        s = datetime.strptime(str(k), "%Y%m%d").date()
        tmax = _clean(d["T2M_MAX"].get(str(k)))
        tmin = _clean(d["T2M_MIN"].get(str(k)))
        # Skip days without temperatures
        if tmin is None or tmax is None:
            continue
        rh = _clean(d.get("RH2M", {}).get(str(k)))
        # 10 m wind (fallback to 2 m)
        w = _clean(d.get("WS10M", {}).get(str(k))) or _clean(
            d.get("WS2M", {}).get(str(k))
        )
        rs = _clean(d.get("ALLSKY_SFC_SW_DWN", {}).get(str(k)))
        pmm = _clean(d.get("PRECTOTCORR", {}).get(str(k)))
        # Derive net radiation using default albedo when Rs present
        rn = None
        if rs is not None:
            rn = max(0.0, rs * (1.0 - DEFAULT_ALBEDO))
        records.append(
            WeatherRecord(
                day=s,
                tmin_c=tmin,
                tmax_c=tmax,
                relative_humidity_pct=rh,
                wind_m_s=w,
                shortwave_mj_m2=rs,
                net_radiation_mj_m2=rn,
                albedo=None,
                precip_mm=pmm,
            )
        )
    return WeatherSeries(records)
