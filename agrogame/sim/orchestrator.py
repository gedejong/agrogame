from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.plant.roots import RootModule, RootParams, RootState
from agrogame.plant.presets import CropPreset
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phosphorus import SoilPhosphorusState
from agrogame.soil.phosphorus.cycle import PhosphorusCycle
from agrogame.soil.chemistry import SoilChemistryModule
from agrogame.atmosphere.et import Evapotranspiration, EtParams, ResidueState
from typing import cast, Any
from datetime import date
from agrogame.sim.calendar import Calendar
from agrogame.soil.water.runtime import WaterRuntime
from agrogame.plant.roots.runtime import RootsRuntime
from agrogame.atmosphere.et.runtime import ETRuntime
from agrogame.atmosphere.et.types import EtState
from agrogame.soil.nitrogen.runtime import NitrogenRuntime
from agrogame.soil.phosphorus.runtime import PhosphorusRuntime
from agrogame.soil.phenology.runtime import PhenologyRuntime
from agrogame.soil.canopy.runtime import CanopyRuntime
from agrogame.soil.microbes import MicrobialBiomassModule, MicrobialParams
from agrogame.soil.microbes.runtime import MicrobesRuntime
from agrogame.sim.management import ManagementPlan
from agrogame.soil.som.runtime import SOMRuntime


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


@dataclass
class SoilSnapshot:
    """Serializable snapshot of soil state between seasons.

    Captures water, nitrogen, phosphorus, microbial, and chemistry pools
    so they can be persisted to disk and restored for multi-season simulation.
    """

    water_theta: list[float] = field(default_factory=list)
    n_nh4: list[float] = field(default_factory=list)
    n_no3: list[float] = field(default_factory=list)
    n_organic: list[float] = field(default_factory=list)
    p_available: list[float] = field(default_factory=list)
    p_fixed: list[float] = field(default_factory=list)
    p_organic: list[float] = field(default_factory=list)
    microbe_c: list[float] = field(default_factory=list)
    microbe_n: list[float] = field(default_factory=list)
    microbe_fungal_fraction: list[float] = field(default_factory=list)
    ph: list[float] = field(default_factory=list)
    crop_history: list[str] = field(default_factory=list)
    som_labile_c: list[float] = field(default_factory=list)
    som_labile_n: list[float] = field(default_factory=list)
    som_intermediate_c: list[float] = field(default_factory=list)
    som_intermediate_n: list[float] = field(default_factory=list)
    som_stable_c: list[float] = field(default_factory=list)
    som_stable_n: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON/YAML persistence."""
        return {
            "water_theta": list(self.water_theta),
            "n_nh4": list(self.n_nh4),
            "n_no3": list(self.n_no3),
            "n_organic": list(self.n_organic),
            "p_available": list(self.p_available),
            "p_fixed": list(self.p_fixed),
            "p_organic": list(self.p_organic),
            "microbe_c": list(self.microbe_c),
            "microbe_n": list(self.microbe_n),
            "microbe_fungal_fraction": list(self.microbe_fungal_fraction),
            "ph": list(self.ph),
            "crop_history": list(self.crop_history),
            "som_labile_c": list(self.som_labile_c),
            "som_labile_n": list(self.som_labile_n),
            "som_intermediate_c": list(self.som_intermediate_c),
            "som_intermediate_n": list(self.som_intermediate_n),
            "som_stable_c": list(self.som_stable_c),
            "som_stable_n": list(self.som_stable_n),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SoilSnapshot:
        """Restore from a plain dict."""
        return cls(
            water_theta=list(data["water_theta"]),
            n_nh4=list(data["n_nh4"]),
            n_no3=list(data["n_no3"]),
            n_organic=list(data["n_organic"]),
            p_available=list(data["p_available"]),
            p_fixed=list(data["p_fixed"]),
            p_organic=list(data["p_organic"]),
            microbe_c=list(data.get("microbe_c", [])),
            microbe_n=list(data.get("microbe_n", [])),
            microbe_fungal_fraction=list(data.get("microbe_fungal_fraction", [])),
            ph=list(data.get("ph", [])),
            crop_history=list(data.get("crop_history", [])),
            som_labile_c=list(data.get("som_labile_c", [])),
            som_labile_n=list(data.get("som_labile_n", [])),
            som_intermediate_c=list(data.get("som_intermediate_c", [])),
            som_intermediate_n=list(data.get("som_intermediate_n", [])),
            som_stable_c=list(data.get("som_stable_c", [])),
            som_stable_n=list(data.get("som_stable_n", [])),
        )


def _default_phen_params() -> CropPhenologyParams:
    return CropPhenologyParams(
        base_temperature_c=8.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )


def _default_canopy_params() -> CanopyParams:
    return CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.01,
    )


class FullSimulationOrchestrator:
    """Event-wired orchestrator including water, chemistry, N and P.

    Keeps responsibilities light: holds modules and provides a convenience
    `step_day` to advance water/N/P using a shared EventBus.

    Supports multi-season simulation via `reset_crop()` and `harvest()`.
    """

    def __init__(
        self,
        profile: SoilProfile,
        event_bus: EventBus | None = None,
        et_params: EtParams | None = None,
        latitude_deg: float = 52.0,
        crop: CropPreset | None = None,
        management_plan: ManagementPlan | None = None,
    ) -> None:
        self.event_bus = event_bus or EventBus()
        self.latitude_deg = latitude_deg
        self._current_crop = crop
        self.crop_history: list[str] = []
        self.management_plan = management_plan or ManagementPlan()
        self._day_counter: int = 0
        # Track last biomass increment for dynamic N/P demand (DSSAT approach:
        # today's demand = yesterday's growth × tissue concentration).
        self._last_biomass_inc_g_m2: float = 0.0

        # Crop parameters (use preset or defaults)
        phen_params = crop.phenology if crop else _default_phen_params()
        canopy_params = crop.canopy if crop else _default_canopy_params()
        root_params = crop.roots if crop else RootParams()

        # Core plant modules
        self.phenology = PhenologyModule(phen_params, event_bus=self.event_bus)
        self.canopy = CanopyModule(canopy_params, event_bus=self.event_bus)
        self.roots = RootModule(root_params, event_bus=self.event_bus)
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
        # Microbial biomass/enzymes (initial scaffold)
        self.microbes = MicrobialBiomassModule(
            MicrobialParams(n_layers=len(profile.layers)), event_bus=self.event_bus
        )
        # Chemistry emits pH events used by N/P
        self.chem = SoilChemistryModule(self.event_bus, n_layers=len(profile.layers))
        # ET model (emits transpiration/evaporation related events via water model)
        self.et = Evapotranspiration(et_params or EtParams())
        # Calendar for phased daily progression
        self.calendar = Calendar(self.event_bus)

        self._wire_runtimes()

    def _wire_runtimes(self) -> None:
        """Subscribe all runtime listeners to the event bus."""
        _ = WaterRuntime(
            self.event_bus, self.water_model, self.profile, self.water_state
        )
        _ = PhenologyRuntime(
            self.event_bus, self.phenology, latitude_deg=self.latitude_deg
        )
        _ = RootsRuntime(
            self.event_bus,
            self.roots,
            self.root_state,
            self.profile,
            self.phenology,
        )
        _ = ETRuntime(
            event_bus=self.event_bus,
            et=self.et,
            profile=self.profile,
            water_state=self.water_state,
            water_model=self.water_model,
            roots_state=self.root_state,
            canopy=self.canopy,
            _evap_state=EtState(),
            _residue=ResidueState(cover_fraction=self.et.params.residue_cover_fraction),
        )
        _ = NitrogenRuntime(self.event_bus, self.n_cycle)
        _ = PhosphorusRuntime(self.event_bus, self.p_cycle)
        self._som_runtime = SOMRuntime(
            self.event_bus, self.profile, self.water_state, self.chem
        )
        _ = MicrobesRuntime(
            self.event_bus,
            self.microbes,
            profile=self.profile,
            water_state=self.water_state,
            chemistry=self.chem,
        )
        _ = CanopyRuntime(self.event_bus, self.canopy)
        # Track biomass increments for dynamic N/P demand computation
        from agrogame.soil.canopy.events import BiomassAccumulated

        self.event_bus.subscribe(BiomassAccumulated, self._on_biomass_accumulated)

    def _som_pool_lists(self, attr: str) -> list[float]:
        """Extract per-layer SOM pool attribute as list."""
        som = self._som_runtime.som
        if som is None:
            return []
        return [
            getattr(getattr(ly, attr.split(".")[0]), attr.split(".")[1])
            for ly in som.state.layers
        ]

    @property
    def som(self) -> Any:
        """Public access to the SOM module (ThreePoolSOM or None)."""
        return self._som_runtime.som

    def snapshot_soil(self) -> SoilSnapshot:
        """Capture current soil state as a serializable snapshot."""
        return SoilSnapshot(
            water_theta=list(self.water_state.theta),
            n_nh4=list(self.n_state.nh4),
            n_no3=list(self.n_state.no3),
            n_organic=list(self.n_state.organic_n),
            p_available=list(self.p_state.available_p),
            p_fixed=list(self.p_state.fixed_p),
            p_organic=list(self.p_state.organic_p),
            microbe_c=[ly.c_kg_ha for ly in self.microbes.state.layers],
            microbe_n=[ly.n_kg_ha for ly in self.microbes.state.layers],
            microbe_fungal_fraction=[
                ly.fungal_fraction for ly in self.microbes.state.layers
            ],
            ph=list(self.chem.ph_by_layer),
            crop_history=list(self.crop_history),
            som_labile_c=self._som_pool_lists("labile.c_kg_ha"),
            som_labile_n=self._som_pool_lists("labile.n_kg_ha"),
            som_intermediate_c=self._som_pool_lists("intermediate.c_kg_ha"),
            som_intermediate_n=self._som_pool_lists("intermediate.n_kg_ha"),
            som_stable_c=self._som_pool_lists("stable.c_kg_ha"),
            som_stable_n=self._som_pool_lists("stable.n_kg_ha"),
        )

    def restore_soil(self, snapshot: SoilSnapshot) -> None:
        """Restore soil state from a snapshot."""
        self.water_state.theta = list(snapshot.water_theta)
        self.n_state.nh4 = list(snapshot.n_nh4)
        self.n_state.no3 = list(snapshot.n_no3)
        self.n_state.organic_n = list(snapshot.n_organic)
        self.p_state.available_p = list(snapshot.p_available)
        self.p_state.fixed_p = list(snapshot.p_fixed)
        self.p_state.organic_p = list(snapshot.p_organic)
        if snapshot.microbe_c:
            for i, ly in enumerate(self.microbes.state.layers):
                ly.c_kg_ha = snapshot.microbe_c[i]
                ly.n_kg_ha = snapshot.microbe_n[i]
                ly.fungal_fraction = snapshot.microbe_fungal_fraction[i]
        if snapshot.ph:
            self.chem._ph = list(snapshot.ph)
        self.crop_history = list(snapshot.crop_history)
        som = self._som_runtime.som
        if snapshot.som_labile_c and som is not None:
            for i, som_ly in enumerate(som.state.layers):
                som_ly.labile.c_kg_ha = snapshot.som_labile_c[i]
                som_ly.labile.n_kg_ha = snapshot.som_labile_n[i]
                som_ly.intermediate.c_kg_ha = snapshot.som_intermediate_c[i]
                som_ly.intermediate.n_kg_ha = snapshot.som_intermediate_n[i]
                som_ly.stable.c_kg_ha = snapshot.som_stable_c[i]
                som_ly.stable.n_kg_ha = snapshot.som_stable_n[i]

    def harvest(self) -> SoilSnapshot:
        """Finalize current crop and return soil state for next season.

        Appends the current crop to history and applies any N fixation
        credit (legumes) to the soil organic N pool in the top layer.
        """
        if self._current_crop is not None:
            self.crop_history.append(self._current_crop.key or self._current_crop.name)
            # Legume N fixation credit — added to organic N for slow
            # release via mineralization (Peoples et al. 2009)
            credit = self._current_crop.n_fixation_credit_kg_ha
            if credit > 0.0:
                self.n_state.organic_n[0] += credit
        return self.snapshot_soil()

    def reset_crop(self, new_crop: CropPreset) -> None:
        """Reset plant state for a new crop, preserving soil state.

        Clears all event subscriptions and re-wires runtimes with fresh
        plant modules. Soil state (water, N, P, chemistry, microbes) is
        preserved across the transition.
        """
        self._current_crop = new_crop
        self._day_counter = 0
        self._last_biomass_inc_g_m2 = 0.0
        # Capture soil state
        soil = self.snapshot_soil()

        # Clear all event subscriptions to avoid stale handlers
        self.event_bus.clear()

        # Fresh plant modules
        self.phenology = PhenologyModule(new_crop.phenology, event_bus=self.event_bus)
        self.canopy = CanopyModule(new_crop.canopy, event_bus=self.event_bus)
        self.roots = RootModule(new_crop.roots, event_bus=self.event_bus)
        self.root_state = RootState()

        # Re-create soil modules that subscribe to events
        self.water_model = CascadingBucketWaterModel(event_bus=self.event_bus)
        self.n_cycle = NitrogenCycle(
            self.event_bus,
            self.n_state,
            water_state=cast(Any, self.water_state),
            profile=cast(Any, self.profile),
        )
        self.p_cycle = PhosphorusCycle(
            self.event_bus,
            self.p_state,
            water_state=cast(Any, self.water_state),
            profile=cast(Any, self.profile),
        )
        self.microbes = MicrobialBiomassModule(
            MicrobialParams(n_layers=len(self.profile.layers)),
            event_bus=self.event_bus,
        )
        self.chem = SoilChemistryModule(
            self.event_bus, n_layers=len(self.profile.layers)
        )
        self.calendar = Calendar(self.event_bus)

        # Restore soil state (water, N, P pools)
        self.restore_soil(soil)

        # Re-wire all runtime listeners
        self._wire_runtimes()

    def _on_biomass_accumulated(self, ev: Any) -> None:
        self._last_biomass_inc_g_m2 = float(ev.increment_g_m2)

    def _compute_nutrient_demand(self) -> tuple[float, float]:
        """Compute N and P demand from previous day's biomass increment.

        Demand = biomass_increment (g/m² → kg/ha) × tissue_conc × demand_factor.
        The demand_factor (2.0) accounts for luxury uptake and the fact that
        newly formed tissue needs higher N concentration than the whole-plant
        average (young leaves ~4% N vs whole-plant 2-3%).
        Ref: DSSAT CERES (Jones et al. 2003); APSIM N-demand algorithm.
        """
        crop = self._current_crop
        if crop is None:
            return 0.0, 0.0
        inc_kg_ha = self._last_biomass_inc_g_m2 * 0.01  # g/m² → kg/ha
        # Factor 2.0: new tissue is N-richer than whole-plant average
        demand_factor = 2.0
        n_demand = inc_kg_ha * crop.tissue_n_conc_kg_kg * demand_factor
        p_demand = inc_kg_ha * crop.tissue_p_conc_kg_kg * demand_factor
        # Small baseline for maintenance uptake when growth is minimal
        n_demand = max(n_demand, 0.01)
        p_demand = max(p_demand, 0.001)
        return n_demand, p_demand

    def step_day(
        self,
        drivers: DailyDrivers,
        *,
        tmin_c: float,
        tmax_c: float,
        par_mj_m2: float,
        sim_date: date | None = None,
        plant_n_demand_kg_ha: float | None = None,
        plant_p_demand_kg_ha: float | None = None,
        target_ph: float = 6.8,
    ) -> None:
        # Execute scheduled management events for this day
        for ev in self.management_plan.events_for_day(self._day_counter):
            if ev.action == "irrigate":
                self.apply_irrigation(ev.params.get("amount_mm", 0.0))
            elif ev.action == "fertilize":
                self.apply_fertilizer(
                    ev.params.get("type", "urea"),
                    ev.params.get("amount_kg_ha", 0.0),
                )
            else:
                raise ValueError(
                    f"Unknown management action {ev.action!r}; "
                    f"choose from 'irrigate', 'fertilize'"
                )

        # Compute dynamic demand from previous day's biomass increment
        # unless the caller explicitly provides values.
        dyn_n, dyn_p = self._compute_nutrient_demand()
        n_demand = plant_n_demand_kg_ha if plant_n_demand_kg_ha is not None else dyn_n
        p_demand = plant_p_demand_kg_ha if plant_p_demand_kg_ha is not None else dyn_p

        # Drive daily progression solely via DayTick phases
        self.calendar.tick(
            sim_date=sim_date or date.today(),
            drivers=drivers,
            target_ph=target_ph,
            tmin_c=tmin_c,
            tmax_c=tmax_c,
            par_mj_m2=par_mj_m2,
            plant_n_demand_kg_ha=n_demand,
            plant_p_demand_kg_ha=p_demand,
        )
        self._day_counter += 1

    # ------------------------------------------------------------------
    # Player actions
    # ------------------------------------------------------------------
    _FERTILIZER_TYPES = frozenset({"urea", "ammonium_nitrate", "tsp"})

    def apply_irrigation(self, amount_mm: float) -> None:
        """Add irrigation water to the soil profile.

        Infiltrates water into soil layers (up to saturation) without
        immediate drainage. Excess above field capacity will cascade
        during the next step_day() call. This means heavy irrigation
        can temporarily raise theta above field capacity.
        """
        if amount_mm <= 0.0:
            return
        self.water_model._infiltrate_layers(self.profile, self.water_state, amount_mm)

    def apply_fertilizer(
        self, fert_type: str, amount_kg_ha: float, layer: int = 0
    ) -> None:
        """Apply fertilizer to a soil layer.

        Args:
            fert_type: One of "urea", "ammonium_nitrate", "tsp".
            amount_kg_ha: Application rate in kg/ha.
            layer: Target soil layer index (default 0 = top layer).

        Raises:
            ValueError: If fert_type is not supported.
        """
        if amount_kg_ha <= 0.0:
            return
        if fert_type not in self._FERTILIZER_TYPES:
            raise ValueError(
                f"Unknown fertilizer type {fert_type!r}; "
                f"choose from {sorted(self._FERTILIZER_TYPES)}"
            )
        if not (0 <= layer < len(self.profile.layers)):
            raise ValueError(
                f"Layer {layer} out of range " f"[0, {len(self.profile.layers)})"
            )
        if fert_type == "urea":
            self.n_cycle.apply_urea(layer, amount_kg_ha)
        elif fert_type == "ammonium_nitrate":
            self.n_cycle.apply_ammonium_nitrate(layer, amount_kg_ha)
        elif fert_type == "tsp":
            self.p_cycle.apply_triple_superphosphate(layer, amount_kg_ha)


def build_full_orchestrator(profile: SoilProfile) -> FullSimulationOrchestrator:
    return FullSimulationOrchestrator(profile)
