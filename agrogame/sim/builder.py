from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phosphorus import SoilPhosphorusState
from agrogame.soil.phosphorus.cycle import PhosphorusCycle
from agrogame.soil.chemistry import SoilChemistryModule
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.plant.roots import RootModule, RootParams, RootState
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams

from .calendar import Calendar


@dataclass
class SimulationApp:
    event_bus: EventBus
    calendar: Calendar


class SimulationBuilder:
    def __init__(self) -> None:
        self._event_bus = EventBus()

    def build(self, profile: SoilProfile) -> SimulationApp:
        # Core soil/water
        _ = CascadingBucketWaterModel(event_bus=self._event_bus)
        water_state = SoilWaterState(profile)

        # Chemistry and nutrients
        _ = SoilChemistryModule(self._event_bus, n_layers=len(profile.layers))
        n_state = SoilNitrogenState(profile)
        _ = NitrogenCycle(
            self._event_bus,
            n_state,
            water_state=water_state,
            profile=profile,
        )
        p_state = SoilPhosphorusState(profile)
        _ = PhosphorusCycle(
            self._event_bus,
            p_state,
            water_state=water_state,
            profile=profile,
        )

        # Plant structure and canopy
        _ = PhenologyModule(
            CropPhenologyParams(
                base_temperature_c=8.0,
                max_temperature_c=35.0,
                thresholds=GrowthStageThresholds(
                    emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
                ),
            ),
            event_bus=self._event_bus,
        )
        _ = CanopyModule(
            CanopyParams(
                extinction_coefficient_k=0.6,
                radiation_use_efficiency_g_per_mj=3.0,
                specific_leaf_area_m2_per_g=0.02,
                lai_max=6.0,
                senescence_rate_per_day=0.01,
            ),
            event_bus=self._event_bus,
        )
        _ = RootModule(RootParams(), event_bus=self._event_bus)
        _ = RootState()  # kept if downstream needs state observers

        # ET constructed (ports wired by listeners at runtime)
        _ = Evapotranspiration(EtParams())

        calendar = Calendar(self._event_bus)
        return SimulationApp(event_bus=self._event_bus, calendar=calendar)
