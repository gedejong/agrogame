from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .cycle import NitrogenCycle
from agrogame.plant.events import NutrientStressComputed
from agrogame.plant.stress import StressCalculator
from agrogame.soil.redox.events import RedoxChanged


@dataclass
class NitrogenRuntime:
    event_bus: EventBus
    cycle: NitrogenCycle
    _stress: StressCalculator | None = None
    _eh_by_layer: list[float] | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self._stress = StressCalculator("liebig")
        self.event_bus.subscribe(RedoxChanged, self._on_redox_changed)

    def _on_redox_changed(self, ev: RedoxChanged) -> None:
        layer = ev.layer
        eh = ev.eh_mv
        if layer is not None and eh is not None:
            if self._eh_by_layer is None:
                self._eh_by_layer = []
            while len(self._eh_by_layer) <= layer:
                self._eh_by_layer.append(200.0)
            self._eh_by_layer[layer] = eh

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        demand = 1.0
        if ev.plant_n_demand_kg_ha is not None:
            demand = float(ev.plant_n_demand_kg_ha)
        tmean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        flux = self.cycle.daily_step(
            temperature_c=tmean,
            plant_demand_kg_ha=demand,
            eh_by_layer=self._eh_by_layer,
        )
        if self._stress is not None:
            stress = self._stress.nutrient_from_uptake_demand(
                uptake_kg_ha=flux.plant_uptake_kg_ha, demand_kg_ha=demand
            )
            self.event_bus.emit(
                NutrientStressComputed(
                    nutrient="N",
                    uptake_kg_ha=flux.plant_uptake_kg_ha,
                    demand_kg_ha=demand,
                    stress=stress,
                )
            )
