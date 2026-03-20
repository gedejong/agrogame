from __future__ import annotations

from datetime import date

from agrogame.weather.types import WeatherRecord, WeatherSeries
from agrogame.weather.utils import sanitize_weather_series, net_radiation_from_shortwave


def test_sanitize_clamps_and_derives_rn() -> None:
    today = date.today()
    r = WeatherRecord(
        day=today,
        tmin_c=-200.0,  # clamp to -60
        tmax_c=200.0,  # clamp to 60
        relative_humidity_pct=150.0,  # clamp to 100
        wind_m_s=-5.0,  # clamp to 0
        shortwave_mj_m2=20.0,
        net_radiation_mj_m2=None,  # should be derived from Rs
        albedo=0.5,
        precip_mm=-1.0,  # clamp to 0
    )
    out = sanitize_weather_series(WeatherSeries([r]))
    o = out.records[0]
    assert o.tmin_c == -60.0
    assert o.tmax_c == 60.0
    assert o.relative_humidity_pct == 100.0
    assert o.wind_m_s == 0.0
    assert o.precip_mm == 0.0
    assert o.shortwave_mj_m2 == 20.0
    assert o.net_radiation_mj_m2 == net_radiation_from_shortwave(20.0, 0.5)


def test_sanitize_power_sentinels_to_none() -> None:
    today = date.today()
    r = WeatherRecord(
        day=today,
        tmin_c=10.0,
        tmax_c=20.0,
        relative_humidity_pct=-999.0,
        wind_m_s=-999.0,
        shortwave_mj_m2=-999.0,
        net_radiation_mj_m2=-999.0,
        albedo=-999.0,  # will be replaced by default
        precip_mm=-999.0,
    )
    out = sanitize_weather_series(WeatherSeries([r]))
    o = out.records[0]
    assert o.relative_humidity_pct is None
    assert o.wind_m_s is None
    assert o.shortwave_mj_m2 is None
    # rn derived from rs, but rs is None here, so rn stays None
    assert o.net_radiation_mj_m2 is None
    # albedo should be filled with default (0..1)
    assert 0.0 <= (o.albedo or 0.0) <= 1.0
    assert o.precip_mm is None
