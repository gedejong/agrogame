from __future__ import annotations

import math
from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.atmosphere.et import Evapotranspiration
from agrogame.params.ports import (
    CanopyView as ETCanopyView,
    RootDistribution as ETRootDistribution,
    WaterProfile as ETWaterProfile,
    WaterState as ETWaterState,
    WaterActuator as ETWaterActuator,
)
from agrogame.atmosphere.et.types import EtState, ResidueState
from agrogame.atmosphere.et.events import EvapotranspirationComputed
from agrogame.plant.stress import StressCalculator
from agrogame.plant.events import WaterStressComputed
from agrogame.weather.constants import NET_RAD_FRACTION

_LN2 = math.log(2.0)


@dataclass
class ETRuntime:
    """Wire Evapotranspiration to the EventBus; partitions ET daily.

    Field types are the shared ports in :mod:`agrogame.params.ports`
    so the atmosphere package never imports concrete soil/plant classes
    directly (#300, #310, ADR-008). The orchestrator passes whatever soil-water
    profile, water state, water model, root state, and canopy module it
    has wired up; structural typing matches them to the ports.
    """

    event_bus: EventBus
    et: Evapotranspiration
    profile: ETWaterProfile
    water_state: ETWaterState
    water_model: ETWaterActuator
    roots_state: ETRootDistribution
    canopy: ETCanopyView
    _stress: StressCalculator | None = None
    _evap_state: EtState = field(default_factory=EtState)
    _residue: ResidueState = field(default_factory=ResidueState)

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self._stress = StressCalculator("liebig")

    def _update_wetting_and_residue(self, ev: DayTick) -> None:
        wetting_mm = 0.0
        if ev.drivers is not None:
            wetting_mm = ev.drivers.rainfall_mm + ev.drivers.irrigation_mm
        if wetting_mm >= self.et.params.wetting_reset_threshold_mm:
            self._evap_state.cumulative_evap_mm = 0.0

        if (
            self._residue.decay_half_life_days > 0.0
            and self._residue.cover_fraction > 0.0
        ):
            self._residue.cover_fraction *= math.exp(
                -_LN2 / self._residue.decay_half_life_days
            )

    def _resolve_climate(self, ev: DayTick) -> tuple[float, float]:
        # NOTE (ADR-014): ``ev.shortwave_mj_m2`` carries incoming shortwave
        # irradiance Rs (MJ m⁻² d⁻¹), fed raw by every entry point; net radiation
        # is derived *here*, inside the consumer (#436 renamed this field from the
        # misleading ``par_mj_m2``).
        temp_mean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            try:
                temp_mean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
            except (TypeError, ValueError):
                temp_mean = 18.0
        # Rn ≈ 0.6·Rs (FAO-56 green-crop range, ADR-014); 12.0 is a net-radiation
        # fallback (MJ m⁻² d⁻¹) when no shortwave driver is present.
        net_radiation = 12.0
        if ev.shortwave_mj_m2 is not None:
            try:
                net_radiation = NET_RAD_FRACTION * float(ev.shortwave_mj_m2)
            except (TypeError, ValueError):
                net_radiation = 12.0
        return temp_mean, net_radiation

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "et":
            return

        self._update_wetting_and_residue(ev)

        root_fracs: list[float] = (
            list(self.roots_state.layer_fractions)
            if self.roots_state.layer_fractions
            else [1.0 / len(self.profile.layers)] * len(self.profile.layers)
        )
        temp_mean, net_radiation = self._resolve_climate(ev)
        et0 = self.et.priestley_taylor(
            temp_mean_c=temp_mean, net_radiation_mj_m2=net_radiation
        )
        comps = self.et.potential_components(et0_mm=et0, lai=self.canopy.state.lai)
        actual = self.et.actual_et(
            self.profile,
            self.water_state,
            self.water_model,
            comps,
            root_fracs,
            evap_state=self._evap_state,
            residue_cover_fraction=self._residue.cover_fraction,
        )
        # Diagnostic-only (*Computed): surface the day's ET partition so
        # observers can accumulate seasonal actual crop ET (E+T). et0 is the
        # model's raw Priestley-Taylor value (not FAO-56-calibrated; #414/#418).
        self.event_bus.emit(
            EvapotranspirationComputed(
                et0_mm=et0,
                evaporation_mm=actual.evaporation_mm,
                transpiration_mm=actual.transpiration_mm,
            )
        )
        if self._stress is not None:
            ws = self._stress.water_from_supply_demand(
                actual_mm=actual.transpiration_mm,
                potential_mm=comps.potential_transp_mm,
            )
            self.event_bus.emit(
                WaterStressComputed(
                    supply_mm=actual.transpiration_mm,
                    demand_mm=comps.potential_transp_mm,
                    stress=ws,
                )
            )
