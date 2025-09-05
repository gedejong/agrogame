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
from typing import cast, Any
from agrogame.soil.water.runtime import WaterRuntime
from agrogame.plant.roots.runtime import RootsRuntime
from agrogame.atmosphere.et.runtime import ETRuntime
from agrogame.soil.nitrogen.runtime import NitrogenRuntime
from agrogame.soil.phosphorus.runtime import PhosphorusRuntime
from agrogame.soil.phenology.runtime import PhenologyRuntime
from agrogame.soil.canopy.runtime import CanopyRuntime
from agrogame.soil.microbes import MicrobialBiomassModule, MicrobialParams
from agrogame.soil.microbes.runtime import MicrobesRuntime


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
            water_state=cast(Any, water_state),
            profile=cast(Any, profile),
        )
        p_state = SoilPhosphorusState(profile)
        _ = PhosphorusCycle(
            self._event_bus,
            p_state,
            water_state=cast(Any, water_state),
            profile=cast(Any, profile),
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
        roots = RootModule(RootParams(), event_bus=self._event_bus)
        roots_state = RootState()

        # ET constructed (ports wired by listeners at runtime)
        et = Evapotranspiration(EtParams())

        calendar = Calendar(self._event_bus)

        # Runtime listeners wiring
        _ = WaterRuntime(self._event_bus, cast(Any, _), profile, water_state)
        _ = PhenologyRuntime(self._event_bus, cast(Any, _))
        _ = RootsRuntime(self._event_bus, roots, roots_state, profile, cast(Any, _))
        _ = ETRuntime(
            self._event_bus,
            et,
            profile,
            water_state,
            cast(Any, _),
            roots_state,
            cast(Any, _),
        )
        _ = NitrogenRuntime(self._event_bus, cast(Any, _))
        _ = PhosphorusRuntime(self._event_bus, cast(Any, _))
        # Microbes wiring for lightweight builder as well
        microbes = MicrobialBiomassModule(
            MicrobialParams(n_layers=len(profile.layers)), event_bus=self._event_bus
        )
        _ = MicrobesRuntime(self._event_bus, microbes)
        _ = CanopyRuntime(self._event_bus, cast(Any, _))
        return SimulationApp(event_bus=self._event_bus, calendar=calendar)
