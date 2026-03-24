from __future__ import annotations

from agrogame.weather.utils import photoperiod_h


def test_equator_near_twelve_hours() -> None:
    pp = photoperiod_h(0.0, 80)  # equinox
    assert 11.5 < pp < 12.5


def test_high_latitude_summer_long_day() -> None:
    pp = photoperiod_h(60.0, 172)  # near summer solstice
    assert pp > 16.0


def test_high_latitude_winter_short_day() -> None:
    pp = photoperiod_h(60.0, 355)  # near winter solstice
    assert pp < 8.0


def test_southern_hemisphere_reversed() -> None:
    north_summer = photoperiod_h(50.0, 172)
    south_summer = photoperiod_h(-50.0, 172)
    assert north_summer > south_summer


def test_polar_clamp_24h() -> None:
    pp = photoperiod_h(85.0, 172)  # arctic summer
    assert pp == 24.0


def test_polar_clamp_0h() -> None:
    pp = photoperiod_h(85.0, 355)  # arctic winter
    assert pp == 0.0


def test_caching_same_result() -> None:
    a = photoperiod_h(52.0, 100)
    b = photoperiod_h(52.0, 100)
    assert a == b
