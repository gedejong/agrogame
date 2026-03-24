from __future__ import annotations

from datetime import date

from agrogame.weather.types import WeatherRecord, WeatherSeries
from agrogame.weather.utils import interpolate_weather_series


def _rec(
    day: int, rh: float | None = None, precip: float | None = None
) -> WeatherRecord:
    return WeatherRecord(
        day=date(2024, 1, day),
        tmin_c=5.0,
        tmax_c=15.0,
        relative_humidity_pct=rh,
        precip_mm=precip,
    )


def test_interior_gap_filled() -> None:
    series = WeatherSeries([_rec(1, rh=60.0), _rec(2, rh=None), _rec(3, rh=80.0)])
    result = interpolate_weather_series(series)
    assert result.records[1].relative_humidity_pct is not None
    assert abs(result.records[1].relative_humidity_pct - 70.0) < 1.0


def test_leading_gap_carry_forward() -> None:
    series = WeatherSeries([_rec(1, rh=None), _rec(2, rh=None), _rec(3, rh=50.0)])
    result = interpolate_weather_series(series)
    assert result.records[0].relative_humidity_pct is not None
    assert abs(result.records[0].relative_humidity_pct - 50.0) < 1.0


def test_trailing_gap_carry_backward() -> None:
    series = WeatherSeries([_rec(1, rh=50.0), _rec(2, rh=None), _rec(3, rh=None)])
    result = interpolate_weather_series(series)
    assert result.records[2].relative_humidity_pct is not None
    assert abs(result.records[2].relative_humidity_pct - 50.0) < 1.0


def test_precip_fills_with_zero() -> None:
    series = WeatherSeries(
        [_rec(1, precip=5.0), _rec(2, precip=None), _rec(3, precip=3.0)]
    )
    result = interpolate_weather_series(series)
    assert result.records[1].precip_mm == 0.0


def test_all_none_field_stays_none_or_default() -> None:
    series = WeatherSeries([_rec(1, rh=None), _rec(2, rh=None)])
    result = interpolate_weather_series(series)
    # All None → stays None after interp (sanitize may leave as None)
    for r in result.records:
        assert r.relative_humidity_pct is None or isinstance(
            r.relative_humidity_pct, float
        )


def test_empty_series() -> None:
    result = interpolate_weather_series(WeatherSeries([]))
    assert len(result.records) == 0


def test_albedo_filled_with_default() -> None:
    series = WeatherSeries(
        [
            WeatherRecord(day=date(2024, 1, 1), tmin_c=5.0, tmax_c=15.0, albedo=None),
            WeatherRecord(day=date(2024, 1, 2), tmin_c=5.0, tmax_c=15.0, albedo=None),
        ]
    )
    result = interpolate_weather_series(series)
    for r in result.records:
        assert r.albedo is not None
        assert abs(r.albedo - 0.23) < 0.01
