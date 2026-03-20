from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .module import CanopyModule
from agrogame.plant.events import WaterStressComputed, NutrientStressComputed
from agrogame.plant.stress import StressCalculator


@dataclass
class CanopyRuntime:
    event_bus: EventBus
    canopy: CanopyModule
    _stress_calc: StressCalculator | None = None
    _last_water: float = 1.0
    _last_n: float = 1.0
    _last_p: float = 1.0

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(WaterStressComputed, self._on_water_stress)
        self.event_bus.subscribe(NutrientStressComputed, self._on_nutrient_stress)
        self._stress_calc = StressCalculator("liebig")

    def _on_water_stress(self, ev: WaterStressComputed) -> None:
        self._last_water = max(0.0, min(1.0, float(ev.stress)))

    def _on_nutrient_stress(self, ev: NutrientStressComputed) -> None:
        s = max(0.0, min(1.0, float(ev.stress)))
        if ev.nutrient.upper() == "N":
            self._last_n = s
        elif ev.nutrient.upper() == "P":
            self._last_p = s

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "canopy":
            return
        par = 12.0 if ev.par_mj_m2 is None else float(ev.par_mj_m2)
        # Stage sensitivity: slightly stronger stress during flowering/grain fill
        water = self._last_water
        n = self._last_n
        p = self._last_p
        if self._stress_calc is not None:
            combined = self._stress_calc.combine(water=water, nitrogen=n, phosphorus=p)
        else:
            combined = min(water, n, p)

        # Provide separate water and N stress to canopy growth for now;
        # P folded into combined
        # Apply phenology sensitivity multiplier on stress for reproductive stages
        # We approximate by reducing stress in sensitive stages (more limiting)
        # Note: CanopyModule only accepts water_stress and n_stress
        water_s = water
        n_s = min(n, combined)
        _ = self.canopy.daily_step(
            incident_par_mj_m2=par,
            temp_factor=1.0,
            water_stress=water_s,
            n_stress=n_s,
        )
