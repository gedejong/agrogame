from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .module import PhenologyModule


@dataclass
class PhenologyRuntime:
    event_bus: EventBus
    phenology: PhenologyModule

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "plant_structure":
            return
        tmin = 8.0 if ev.tmin_c is None else float(ev.tmin_c)
        tmax = 20.0 if ev.tmax_c is None else float(ev.tmax_c)
        self.phenology.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
