from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.atmosphere.et import Evapotranspiration
from agrogame.atmosphere.et.ports import (
    WaterProfile as ETWaterProfile,
    WaterState as ETWaterState,
    WaterActuator as ETWaterActuator,
)
from agrogame.plant.roots.types import RootState
from agrogame.soil.canopy.module import CanopyModule
from typing import cast


@dataclass
class ETRuntime:
    event_bus: EventBus
    et: Evapotranspiration
    profile: SoilProfile
    water_state: SoilWaterState
    water_model: CascadingBucketWaterModel
    roots_state: RootState
    canopy: CanopyModule

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "et":
            return
        # Compute ET0 and actual ET using current canopy LAI and root fractions
        # Use DayTick weather (tmin/tmax, PAR) when available to avoid constants
        root_fracs = (
            self.roots_state.layer_fractions
            if self.roots_state.layer_fractions
            else [1.0 / len(self.profile.layers)] * len(self.profile.layers)
        )
        # Derive mean temperature and net radiation from event payloads when possible
        temp_mean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            try:
                temp_mean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
            except Exception:
                temp_mean = 18.0
        # Convert PAR to net radiation using typical conversion if provided
        net_radiation = 12.0
        if ev.par_mj_m2 is not None:
            try:
                net_radiation = float(ev.par_mj_m2) / 0.48
            except Exception:
                net_radiation = 12.0
        et0 = self.et.priestley_taylor(
            temp_mean_c=temp_mean, net_radiation_mj_m2=net_radiation
        )
        comps = self.et.potential_components(et0_mm=et0, lai=self.canopy.state.lai)
        _ = self.et.actual_et(
            cast(ETWaterProfile, self.profile),
            cast(ETWaterState, self.water_state),
            cast(ETWaterActuator, self.water_model),
            comps,
            root_fracs,
        )
