from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .module import CanopyModule


@dataclass
class CanopyRuntime:
    event_bus: EventBus
    canopy: CanopyModule

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "canopy":
            return
        par = 12.0 if ev.par_mj_m2 is None else float(ev.par_mj_m2)
        _ = self.canopy.daily_step(
            incident_par_mj_m2=par,
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )
