from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from .cycle import SulfurCycle
from agrogame.plant.events import NutrientStressComputed
from agrogame.plant.stress import StressCalculator

# Soil temperature used for ticks that carry no air temperatures (unit wiring,
# legacy callers): a temperate mid-season value.
FALLBACK_SOIL_TEMPERATURE_C: float = 18.0


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
        flux = self.cycle.daily_step(
            temperature_c=self._soil_temperature_c(ev), plant_demand_kg_ha=demand
        )
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

    @staticmethod
    def _soil_temperature_c(ev: DayTick) -> float:
        """Daily mean air temperature as the soil-temperature proxy for S turnover.

        The same proxy drives the gas-diffusion and nitrogen runtimes, so the
        temperature response of S mineralisation follows the climate instead
        of a fixed value.
        """
        if ev.tmin_c is None or ev.tmax_c is None:
            return FALLBACK_SOIL_TEMPERATURE_C
        return 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
