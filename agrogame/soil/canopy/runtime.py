from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .module import CanopyModule
from .params import cardinal_temp_factor
from agrogame.plant.events import WaterStressComputed, NutrientStressComputed
from agrogame.plant.stress import StressCalculator
from agrogame.weather.utils import saturation_vapor_pressure_kpa


@dataclass
class CanopyRuntime:
    event_bus: EventBus
    canopy: CanopyModule
    _stress_calc: StressCalculator | None = None
    _last_water: float = 1.0
    _last_n: float = 1.0
    _last_p: float = 1.0
    # Initialized properly in __post_init__ using configurable window size
    _stress_history: deque[float] = field(init=False)
    _consecutive_wilt_days: int = 0

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(WaterStressComputed, self._on_water_stress)
        self.event_bus.subscribe(NutrientStressComputed, self._on_nutrient_stress)
        self._stress_calc = StressCalculator("liebig")
        self._stress_history = deque(maxlen=self.canopy.params.stress_memory_days)

    def _on_water_stress(self, ev: WaterStressComputed) -> None:
        self._last_water = max(0.0, min(1.0, float(ev.stress)))

    def _on_nutrient_stress(self, ev: NutrientStressComputed) -> None:
        s = max(0.0, min(1.0, float(ev.stress)))
        if ev.nutrient.upper() == "N":
            self._last_n = s
        elif ev.nutrient.upper() == "P":
            self._last_p = s

    def _compute_temp_factor(self, ev: DayTick) -> float:
        if ev.tmin_c is None or ev.tmax_c is None:
            return 1.0
        tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        p = self.canopy.params
        return cardinal_temp_factor(tmean, p.temp_base_c, p.temp_opt_c, p.temp_max_c)

    def _vpd_rue_factor(self, ev: DayTick) -> float:
        """Reduce RUE under high VPD using FAO-56 tmin-based dewpoint.

        VPD ≈ SVP(tmean) - SVP(tmin), following FAO-56 recommendation
        that tmin approximates dewpoint temperature. No circular
        dependency on water stress.
        """
        if ev.tmin_c is None or ev.tmax_c is None:
            return 1.0
        tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        vpd = saturation_vapor_pressure_kpa(tmean) - saturation_vapor_pressure_kpa(
            float(ev.tmin_c)
        )
        vpd = max(0.0, vpd)
        p = self.canopy.params
        excess = max(0.0, vpd - p.vpd_rue_ref_kpa)
        return max(0.2, 1.0 - p.vpd_rue_slope * excess)

    def _update_stress_memory(self, water_stress: float) -> float:
        """Track stress history and return running-average stress."""
        self._stress_history.append(water_stress)
        if not self._stress_history:
            return water_stress
        return sum(self._stress_history) / len(self._stress_history)

    def _check_wilt_damage(self, water_stress: float) -> None:
        """Apply irreversible LAI loss after prolonged severe stress.

        Fires repeatedly every wilt_days_for_damage consecutive days
        of severe stress — intentional compounding to model progressive
        leaf death during extended drought.
        """
        p = self.canopy.params
        if water_stress < p.wilt_stress_threshold:
            self._consecutive_wilt_days += 1
        else:
            self._consecutive_wilt_days = 0
        if self._consecutive_wilt_days >= p.wilt_days_for_damage:
            loss = self.canopy.state.lai * p.wilt_lai_loss_fraction
            self.canopy.state.lai = max(0.0, self.canopy.state.lai - loss)
            self._consecutive_wilt_days = 0

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "canopy":
            return
        par = 12.0 if ev.par_mj_m2 is None else float(ev.par_mj_m2)
        water = self._last_water
        n = self._last_n
        p = self._last_p
        if self._stress_calc is not None:
            combined = self._stress_calc.combine(water=water, nitrogen=n, phosphorus=p)
        else:
            combined = min(water, n, p)

        avg_water = self._update_stress_memory(water)
        vpd_factor = self._vpd_rue_factor(ev)
        effective_water = min(water, avg_water) * vpd_factor

        n_s = min(n, combined)
        tf = self._compute_temp_factor(ev)
        _ = self.canopy.daily_step(
            incident_par_mj_m2=par,
            temp_factor=tf,
            water_stress=effective_water,
            n_stress=n_s,
        )
        # Wilt check after growth: damage represents end-of-day leaf death,
        # so today's growth uses pre-damage LAI. Next day sees reduced canopy.
        self._check_wilt_damage(water)
