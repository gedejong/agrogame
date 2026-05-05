from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .cycle import PhosphorusCycle
from agrogame.plant.events import NutrientStressComputed
from agrogame.plant.stress import StressCalculator
from agrogame.soil.redox.events import RedoxChanged
from agrogame.soil.redox.params import RedoxParams


@dataclass
class PhosphorusRuntime:
    """Wire PhosphorusCycle to the EventBus; subscribes to DayTick + RedoxChanged."""

    event_bus: EventBus
    cycle: PhosphorusCycle
    _stress: StressCalculator | None = None
    _redox_params: RedoxParams = field(default_factory=RedoxParams)

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self._stress = StressCalculator("liebig")
        self.event_bus.subscribe(RedoxChanged, self._on_redox_changed)

    def _on_redox_changed(self, ev: RedoxChanged) -> None:
        """Release fixed P when Eh drops below Fe(III) reduction threshold.

        Ref: Patrick & Khalid 1974, Science — Fe-P release under reducing.
        """
        if ev.eh_mv >= 100.0:
            return
        state = self.cycle.state
        if ev.layer >= len(state.fixed_p):
            return
        # Release fraction of fixed P proportional to reducing severity
        release_frac = self._redox_params.fe_p_release_fraction * min(
            1.0, (100.0 - ev.eh_mv) / 200.0
        )
        released = state.fixed_p[ev.layer] * release_frac
        if released > 0.0:
            state.fixed_p[ev.layer] -= released
            state.available_p[ev.layer] += released

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        demand = 0.5
        if ev.plant_p_demand_kg_ha is not None:
            demand = float(ev.plant_p_demand_kg_ha)
        flux = self.cycle.daily_step(temperature_c=18.0, plant_demand_kg_ha=demand)
        if self._stress is not None:
            stress = self._stress.nutrient_from_uptake_demand(
                uptake_kg_ha=flux.plant_uptake_kg_ha, demand_kg_ha=demand
            )
            self.event_bus.emit(
                NutrientStressComputed(
                    nutrient="P",
                    uptake_kg_ha=flux.plant_uptake_kg_ha,
                    demand_kg_ha=demand,
                    stress=stress,
                )
            )
