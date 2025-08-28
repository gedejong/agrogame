from __future__ import annotations

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import urllib.request

from .types import WeatherRecord, WeatherSeries


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
                    )
                )
            except Exception as e:  # noqa: BLE001
                raise ValueError(f"CSV parse error at line {i}: {e}") from e
    return WeatherSeries(rows)


def _load_json(path: Path) -> WeatherSeries:
    data = json.loads(path.read_text())
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
                )
            )
        except Exception as e:  # noqa: BLE001
            raise ValueError(f"JSON parse error at index {i}: {e}") from e
    return WeatherSeries(rows)


def _opt_float(v: Optional[str | float]) -> Optional[float]:
    if v is None or v == "":
        return None
    return float(v)


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
        "parameters": (
            "T2M_MAX,T2M_MIN,RH2M,WIND_SPEED,ALLSKY_SFC_SW_DWN,ALLSKY_SFC_LW_NET_DWN"
        ),
        "format": "JSON",
    }
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point?"
        f"parameters={params['parameters']}"
        f"&community=AG&longitude={longitude}&latitude={latitude}"
        f"&start={params['start']}&end={params['end']}&format=JSON"
    )
    with urllib.request.urlopen(url, timeout=60) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))

    d = payload["properties"]["parameter"]
    days = sorted(int(k) for k in d["T2M_MAX"].keys())
    records: List[WeatherRecord] = []
    for k in days:
        s = datetime.strptime(str(k), "%Y%m%d").date()
        tmax = float(d["T2M_MAX"][str(k)])
        tmin = float(d["T2M_MIN"][str(k)])
        rh = _opt_float(d.get("RH2M", {}).get(str(k)))
        w = _opt_float(d.get("WIND_SPEED", {}).get(str(k)))
        rs = _opt_float(d.get("ALLSKY_SFC_SW_DWN", {}).get(str(k)))
        # NASA POWER provides net longwave; approximate net radiation if Rs present
        rn = None
        if rs is not None:
            lw_net = _opt_float(d.get("ALLSKY_SFC_LW_NET_DWN", {}).get(str(k))) or 0.0
            rn = max(0.0, rs + lw_net)
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
            )
        )
    return WeatherSeries(records)
