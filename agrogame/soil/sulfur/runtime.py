from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from .cycle import SulfurCycle
from agrogame.plant.events import NutrientStressComputed
from agrogame.plant.stress import StressCalculator


@dataclass
class SulfurRuntime:
    """Wire SulfurCycle to the EventBus; subscribes to DayTick.

    Non-redox by design (#212): unlike the phosphorus runtime, sulfur does
    not subscribe to ``RedoxChanged`` — redox-driven S transformations are a
    separate sub-issue.
    """

    event_bus: EventBus
    cycle: SulfurCycle
    _stress: StressCalculator | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self._stress = StressCalculator("liebig")

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        demand = 0.05
        if ev.plant_s_demand_kg_ha is not None:
            demand = float(ev.plant_s_demand_kg_ha)
        flux = self.cycle.daily_step(temperature_c=18.0, plant_demand_kg_ha=demand)
        if self._stress is not None:
            stress = self._stress.nutrient_from_uptake_demand(
                uptake_kg_ha=flux.plant_uptake_kg_ha, demand_kg_ha=demand
            )
            self.event_bus.emit(
                NutrientStressComputed(
                    nutrient="S",
                    uptake_kg_ha=flux.plant_uptake_kg_ha,
                    demand_kg_ha=demand,
                    stress=stress,
                )
            )
