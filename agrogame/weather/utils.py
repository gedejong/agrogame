from __future__ import annotations

import functools
import math

from .constants import (
    FAO_SVP_A_KPA,
    FAO_SVP_B,
    FAO_SVP_C,
    DEFAULT_ALBEDO,
    EARTH_AXIAL_TILT_RAD,
)
from .types import WeatherRecord, WeatherSeries


@functools.lru_cache(maxsize=512)
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


@functools.lru_cache(maxsize=512)
def photoperiod_h(latitude_deg: float, day_of_year: int) -> float:
    """Daylength in hours from latitude and day of year (Spencer 1971)."""
    lat_rad = math.radians(latitude_deg)
    declination = EARTH_AXIAL_TILT_RAD * math.sin(
        2.0 * math.pi / 365.0 * day_of_year - 1.405
    )
    cos_omega = -math.tan(lat_rad) * math.tan(declination)
    # Polar day / polar night
    if cos_omega < -1.0:
        return 24.0
    if cos_omega > 1.0:
        return 0.0
    omega_s = math.acos(cos_omega)
    return max(0.0, min(24.0, 24.0 / math.pi * omega_s))


def _interp_field(values: list[float | None]) -> list[float | None]:
    """Linear interpolation for a list of optional floats."""
    n = len(values)
    result: list[float | None] = list(values)
    # Find non-None indices
    known = [(i, v) for i, v in enumerate(values) if v is not None]
    if not known:
        return result
    # Fill leading Nones with first known value
    first_idx, first_val = known[0]
    for i in range(first_idx):
        result[i] = first_val
    # Fill trailing Nones with last known value
    last_idx, last_val = known[-1]
    for i in range(last_idx + 1, n):
        result[i] = last_val
    # Linear interpolation between known points
    for k in range(len(known) - 1):
        i0, v0 = known[k]
        i1, v1 = known[k + 1]
        for i in range(i0 + 1, i1):
            t = (i - i0) / (i1 - i0)
            result[i] = v0 + t * (v1 - v0)
    return result


def interpolate_weather_series(series: WeatherSeries) -> WeatherSeries:
    """Fill None values in a weather series.

    Continuous fields use linear interpolation; precipitation fills with 0.0;
    albedo fills with DEFAULT_ALBEDO. Result is sanitized afterward.
    """
    if not series.records:
        return series
    n = len(series.records)
    # Extract columns
    rh = [r.relative_humidity_pct for r in series.records]
    wind = [r.wind_m_s for r in series.records]
    sw = [r.shortwave_mj_m2 for r in series.records]
    rn = [r.net_radiation_mj_m2 for r in series.records]
    # Interpolate continuous fields
    rh_f = _interp_field(rh)
    wind_f = _interp_field(wind)
    sw_f = _interp_field(sw)
    rn_f = _interp_field(rn)
    records = []
    for i in range(n):
        r = series.records[i]
        records.append(
            WeatherRecord(
                day=r.day,
                tmin_c=r.tmin_c,
                tmax_c=r.tmax_c,
                relative_humidity_pct=rh_f[i],
                wind_m_s=wind_f[i],
                shortwave_mj_m2=sw_f[i],
                net_radiation_mj_m2=rn_f[i],
                albedo=r.albedo if r.albedo is not None else DEFAULT_ALBEDO,
                precip_mm=r.precip_mm if r.precip_mm is not None else 0.0,
            )
        )
    return sanitize_weather_series(WeatherSeries(records))
