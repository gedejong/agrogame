from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .cycle import NitrogenCycle


@dataclass
class NitrogenRuntime:
    event_bus: EventBus
    cycle: NitrogenCycle

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        # Temperature to daily_step can be derived from weather later; fallback 18C
        _ = self.cycle.daily_step(temperature_c=18.0, plant_demand_kg_ha=1.0)
