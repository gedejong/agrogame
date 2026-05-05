from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.weather.utils import photoperiod_h
from .module import PhenologyModule


@dataclass
class PhenologyRuntime:
    """Wire PhenologyModule to the EventBus; subscribes to DayTick to advance GDD."""

    event_bus: EventBus
    phenology: PhenologyModule
    latitude_deg: float = 52.0

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "plant_structure":
            return
        tmin = 8.0 if ev.tmin_c is None else float(ev.tmin_c)
        tmax = 20.0 if ev.tmax_c is None else float(ev.tmax_c)
        doy = ev.sim_date.timetuple().tm_yday
        pp = photoperiod_h(self.latitude_deg, doy)
        self.phenology.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=pp)
