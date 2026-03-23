from __future__ import annotations

import math
from .constants import FAO_SVP_A_KPA, FAO_SVP_B, FAO_SVP_C, DEFAULT_ALBEDO
from .types import WeatherRecord, WeatherSeries


def saturation_vapor_pressure_kpa(temp_c: float) -> float:
    return FAO_SVP_A_KPA * math.exp(FAO_SVP_B * temp_c / (temp_c + FAO_SVP_C))


def vpd_kpa(temp_mean_c: float, relative_humidity_pct: float) -> float:
    es = saturation_vapor_pressure_kpa(temp_mean_c)
    ea = es * max(0.0, min(1.0, relative_humidity_pct / 100.0))
    return max(0.0, es - ea)


def net_radiation_from_shortwave(
    rs_mj_m2: float,
    albedo: float,
    lw_net_mj_m2: float = 0.0,
) -> float:
    """Approximate net radiation from shortwave and albedo plus optional LW net."""
    return max(0.0, rs_mj_m2 * (1.0 - max(0.0, min(1.0, albedo))) + lw_net_mj_m2)


def _clean_optional(
    value: float | None, lo: float | None = None, hi: float | None = None
) -> float | None:
    """Return None for sentinel/missing values, else clamp to [lo, hi]."""
    if value is None or float(value) <= -900.0:
        return None
    v = float(value)
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _sanitize_record(r: WeatherRecord) -> WeatherRecord:
    tmin = max(-60.0, min(60.0, float(r.tmin_c)))
    tmax = max(-60.0, min(60.0, float(r.tmax_c)))
    rh = _clean_optional(r.relative_humidity_pct, 0.0, 100.0)
    wind = _clean_optional(r.wind_m_s, 0.0)
    rs = _clean_optional(r.shortwave_mj_m2, 0.0)
    albedo = _clean_optional(r.albedo, 0.0, 1.0)
    if albedo is None:
        albedo = DEFAULT_ALBEDO
    rn = _clean_optional(r.net_radiation_mj_m2)
    if rn is None and rs is not None:
        rn = net_radiation_from_shortwave(rs, albedo)
    rn = None if rn is None else max(0.0, float(rn))
    pmm = _clean_optional(r.precip_mm, 0.0)
    return WeatherRecord(
        day=r.day,
        tmin_c=tmin,
        tmax_c=tmax,
        relative_humidity_pct=rh,
        wind_m_s=wind,
        shortwave_mj_m2=rs,
        net_radiation_mj_m2=rn,
        albedo=albedo,
        precip_mm=pmm,
    )


def sanitize_weather_series(series: WeatherSeries) -> WeatherSeries:
    """Return a sanitized copy of a weather series.

    - Converts POWER sentinels (<= -900) to None
    - Clamps temperatures to [-60, 60] deg C
    - Clamps RH to [0, 100] % if provided
    - Clamps wind to >= 0 if provided
    - Clamps radiation and precipitation to >= 0
    - Derives net radiation from shortwave if missing
    - Fills missing albedo with DEFAULT_ALBEDO
    """
    return WeatherSeries([_sanitize_record(r) for r in series.records])
