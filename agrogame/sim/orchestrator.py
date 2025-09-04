from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.plant.roots import RootModule, RootParams, RootState
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phosphorus import SoilPhosphorusState
from agrogame.soil.phosphorus.cycle import PhosphorusCycle
from agrogame.soil.chemistry import SoilChemistryModule
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.atmosphere.et.ports import (
    WaterProfile as ETWaterProfile,
    WaterState as ETWaterState,
    WaterActuator as ETWaterActuator,
)
from typing import cast, Any


class SimulationOrchestrator:
    """Minimal orchestrator wiring a shared EventBus for modules.

    Currently integrates phenology and canopy. Extend later with water and nutrients.
    """

    def __init__(
        self,
        phenology_params: CropPhenologyParams,
        canopy_params: CanopyParams,
        event_bus: EventBus | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.phenology = PhenologyModule(phenology_params, event_bus=self.event_bus)
        self.canopy = CanopyModule(canopy_params, event_bus=self.event_bus)
        self.roots = RootModule(RootParams(), event_bus=self.event_bus)
        self.root_state = RootState()

    def step_day(
        self,
        tmin_c: float,
        tmax_c: float,
        par_mj_m2: float,
        photoperiod_h: float = 12.0,
        temp_factor: float = 1.0,
        water_stress: float = 1.0,
        n_stress: float = 1.0,
    ) -> None:
        self.phenology.update_daily(
            tmin_c=tmin_c, tmax_c=tmax_c, photoperiod_h=photoperiod_h
        )
        _ = self.canopy.daily_step(
            incident_par_mj_m2=par_mj_m2,
            temp_factor=temp_factor,
            water_stress=water_stress,
            n_stress=n_stress,
        )
        # Simple demo: allocate a fraction of biomass to roots, update roots
        # In a full coupling, we'd pass real nutrient signals and constraints
        stage = self.phenology.state.stage
        _ = self.roots.daily_step(
            state=self.root_state,
            profile=None,  # type: ignore[arg-type]
            stage=stage,
            daily_root_biomass_g_m2=0.0,
            nutrient_signal=None,
            constraints=None,
        )


def build_default_orchestrator() -> SimulationOrchestrator:
    phen = CropPhenologyParams(
        base_temperature_c=8.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )
    can = CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.01,
    )
    return SimulationOrchestrator(phen, can)


class FullSimulationOrchestrator:
    """Event-wired orchestrator including water, chemistry, N and P.

    Keeps responsibilities light: holds modules and provides a convenience
    `step_day` to advance water/N/P using a shared EventBus.
    """

    def __init__(self, profile: SoilProfile, event_bus: EventBus | None = None) -> None:
        self.event_bus = event_bus or EventBus()
        # Core plant modules
        self.phenology = PhenologyModule(
            CropPhenologyParams(
                base_temperature_c=8.0,
                max_temperature_c=35.0,
                thresholds=GrowthStageThresholds(
                    emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
                ),
            ),
            event_bus=self.event_bus,
        )
        self.canopy = CanopyModule(
            CanopyParams(
                extinction_coefficient_k=0.6,
                radiation_use_efficiency_g_per_mj=3.0,
                specific_leaf_area_m2_per_g=0.02,
                lai_max=6.0,
                senescence_rate_per_day=0.01,
            ),
            event_bus=self.event_bus,
        )
        self.roots = RootModule(RootParams(), event_bus=self.event_bus)
        self.root_state = RootState()

        # Soil/water/chemistry/nutrients
        self.profile = profile
        self.water_model = CascadingBucketWaterModel(event_bus=self.event_bus)
        self.water_state = SoilWaterState(profile)

        self.n_state = SoilNitrogenState(profile)
        self.n_cycle = NitrogenCycle(
            self.event_bus,
            self.n_state,
            water_state=cast(Any, self.water_state),
            profile=cast(Any, profile),
        )
        self.p_state = SoilPhosphorusState(profile)
        self.p_cycle = PhosphorusCycle(
            self.event_bus,
            self.p_state,
            water_state=cast(Any, self.water_state),
            profile=cast(Any, profile),
        )
        # Chemistry emits pH events used by N/P
        self.chem = SoilChemistryModule(self.event_bus, n_layers=len(profile.layers))
        # ET model (emits transpiration/evaporation related events via water model)
        self.et = Evapotranspiration(EtParams())

    def step_day(
        self,
        drivers: DailyDrivers,
        *,
        tmin_c: float,
        tmax_c: float,
        par_mj_m2: float,
        plant_n_demand_kg_ha: float = 1.0,
        plant_p_demand_kg_ha: float = 0.5,
        target_ph: float = 6.8,
    ) -> None:
        # Update phenology first (can influence canopy later)
        self.phenology.update_daily(tmin_c=tmin_c, tmax_c=tmax_c, photoperiod_h=12.0)

        # Chemistry buffering towards target pH (emits SoilPHUpdated per layer)
        self.chem.daily_buffering(target_ph=target_ph)

        # Water model progresses storage (rain/evap placeholder handled via ET below)
        _ = self.water_model.update_daily(self.profile, self.water_state, drivers)

        # Roots update first to obtain fractions for ET
        _ = self.roots.daily_step(
            self.root_state, self.profile, self.phenology.state.stage
        )
        root_fracs = (
            self.root_state.layer_fractions
            if self.root_state.layer_fractions
            else [1.0 / len(self.profile.layers)] * len(self.profile.layers)
        )
        # ET actuals to trigger transpiration extraction events
        temp_mean = 0.5 * (tmin_c + tmax_c)
        et0 = self.et.priestley_taylor(
            temp_mean_c=temp_mean, net_radiation_mj_m2=par_mj_m2
        )
        comps = self.et.potential_components(et0_mm=et0, lai=self.canopy.state.lai)
        _ = self.et.actual_et(
            cast(ETWaterProfile, self.profile),
            cast(ETWaterState, self.water_state),
            cast(ETWaterActuator, self.water_model),
            comps,
            root_fracs,
        )

        # Nutrients daily steps; pH is already provided via events
        _ = self.n_cycle.daily_step(
            temperature_c=0.5 * (tmin_c + tmax_c),
            plant_demand_kg_ha=plant_n_demand_kg_ha,
        )
        _ = self.p_cycle.daily_step(
            temperature_c=0.5 * (tmin_c + tmax_c),
            plant_demand_kg_ha=plant_p_demand_kg_ha,
        )

        # Canopy growth step to emit canopy events
        _ = self.canopy.daily_step(
            incident_par_mj_m2=par_mj_m2,
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )


def build_full_orchestrator(profile: SoilProfile) -> FullSimulationOrchestrator:
    return FullSimulationOrchestrator(profile)
