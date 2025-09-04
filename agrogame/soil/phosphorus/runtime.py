from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .cycle import PhosphorusCycle


@dataclass
class PhosphorusRuntime:
    event_bus: EventBus
    cycle: PhosphorusCycle

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        demand = 0.5
        if ev.plant_p_demand_kg_ha is not None:
            demand = float(ev.plant_p_demand_kg_ha)
        _ = self.cycle.daily_step(temperature_c=18.0, plant_demand_kg_ha=demand)
