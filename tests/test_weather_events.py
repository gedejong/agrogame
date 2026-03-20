from __future__ import annotations

from datetime import date

from agrogame.events import EventBus
from agrogame.weather.events import DailyWeather
from agrogame.weather.types import WeatherRecord, WeatherSeries
from agrogame.weather.module import WeatherModule


def test_daily_weather_event_emission() -> None:
    bus = EventBus()
    captured: list[DailyWeather] = []
    bus.subscribe(DailyWeather, lambda e: captured.append(e))

    series = WeatherSeries(
        [
            WeatherRecord(
                day=date(2024, 6, 1),
                tmin_c=10,
                tmax_c=22,
                relative_humidity_pct=60,
                wind_m_s=2.5,
                shortwave_mj_m2=18,
                net_radiation_mj_m2=14,
                precip_mm=3.0,
            )
        ]
    )
    mod = WeatherModule(series, bus)
    evt = mod.emit_for_day(0)

    assert evt is not None and len(captured) == 1
    as_dict = evt.to_dict()
    assert as_dict["tmax_c"] == 22
    assert as_dict["precip_mm"] == 3.0
