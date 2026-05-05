from __future__ import annotations


from agrogame.events import EventBus
from .events import DailyWeather
from .types import WeatherSeries


class WeatherModule:
    """Pure-logic weather emitter — fires DailyWeather for a given day index."""

    def __init__(self, series: WeatherSeries, event_bus: EventBus) -> None:
        self.series = series
        self.event_bus = event_bus

    def emit_for_day(self, day_index: int) -> DailyWeather | None:
        if day_index < 0 or day_index >= len(self.series.records):
            return None
        rec = self.series.records[day_index]
        evt = DailyWeather(
            day=rec.day,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            relative_humidity_pct=rec.relative_humidity_pct,
            wind_m_s=rec.wind_m_s,
            net_radiation_mj_m2=rec.net_radiation_mj_m2,
            shortwave_mj_m2=rec.shortwave_mj_m2,
            precip_mm=rec.precip_mm,
        )
        self.event_bus.emit(evt)
        return evt
