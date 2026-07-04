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
from agrogame.plant.nitrogen import (
    PlantNitrogenModule,
    PlantNitrogenParams,
    PlantNitrogenState,
)
from agrogame.plant.nitrogen.runtime import PlantNitrogenRuntime
from agrogame.plant.presets import CropPreset
from agrogame.params.ports import SoilProfileView
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.nitrogen.params import NitrogenRateParams
from agrogame.soil.phosphorus import SoilPhosphorusState
from agrogame.soil.phosphorus.cycle import PhosphorusCycle
from agrogame.soil.chemistry import SoilChemistryModule
from agrogame.atmosphere.et import Evapotranspiration, EtParams, ResidueState
from typing import Any
from collections.abc import Callable
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
from agrogame.soil.som.events import CO2Respired
from agrogame.soil.som.runtime import SOMRuntime
from agrogame.soil.redox import RedoxModule, RedoxParams, RedoxState
from agrogame.soil.redox.runtime import RedoxRuntime
from agrogame.soil.micronutrients import (
    MicronutrientCycle,
    MicronutrientParams,
    MicronutrientState,
)
from agrogame.soil.micronutrients.runtime import MicronutrientRuntime
from agrogame.soil.aggregation import (
    AggregationModule,
    SoilAggregationParams,
    SoilAggregationState,
)
from agrogame.soil.aggregation.runtime import AggregationRuntime
from agrogame.soil.pore_network import (
    PoreNetworkModule,
    PoreNetworkParams,
    PoreNetworkState,
)
from agrogame.soil.biopores import (
    BioporeModule,
    BioporeParams,
    BioporeState,
    BioporesRuntime,
)
from agrogame.soil.gas_diffusion import (
    GasDiffusionModule,
    GasDiffusionParams,
    GasDiffusionState,
)
from agrogame.soil.gas_diffusion.runtime import GasDiffusionRuntime
from agrogame.soil.pore_network.runtime import PoreNetworkRuntime


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
        fx = self.canopy.daily_step(
            incident_par_mj_m2=par_mj_m2,
            temp_factor=temp_factor,
            water_stress=water_stress,
            n_stress=n_stress,
            root_allocation_fraction=self.roots.params.root_allocation_fraction,
        )
        # Route the below-ground share the canopy already reserved from today's
        # single assimilate pool to roots (#337): a true source–sink split, not
        # an add-on. In a full coupling, we'd also pass real nutrient signals.
        stage = self.phenology.state.stage
        _ = self.roots.daily_step(
            state=self.root_state,
            profile=None,  # type: ignore[arg-type]
            stage=stage,
            daily_root_biomass_g_m2=max(0.0, fx.root_increment_g_m2),
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

    The whole-shoot plant-N stock (#360) is intentionally *not* captured
    here: it is a within-season plant property that resets to zero for each
    new crop (a fresh seedling holds ~no shoot N). ``reset_crop`` rebuilds
    ``plant_n_state`` fresh, so no round-trip is needed.
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
    redox_eh: list[float] = field(default_factory=list)
    micro_fe_avail: list[float] = field(default_factory=list)
    micro_zn_avail: list[float] = field(default_factory=list)
    micro_mn_avail: list[float] = field(default_factory=list)
    micro_fe_total: list[float] = field(default_factory=list)
    micro_zn_total: list[float] = field(default_factory=list)
    micro_mn_total: list[float] = field(default_factory=list)
    agg_micro: list[float] = field(default_factory=list)
    agg_meso: list[float] = field(default_factory=list)
    agg_macro: list[float] = field(default_factory=list)
    # Pore-network chain (#284). All four fields default to empty
    # lists so loading a pre-#284 save initializes them from defaults
    # without crashing.
    pore_network: dict[str, Any] = field(default_factory=dict)
    biopore: dict[str, Any] = field(default_factory=dict)
    gas_diffusion: dict[str, Any] = field(default_factory=dict)
    water_theta_macro: list[float] = field(default_factory=list)

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
            "redox_eh": list(self.redox_eh),
            "micro_fe_avail": list(self.micro_fe_avail),
            "micro_zn_avail": list(self.micro_zn_avail),
            "micro_mn_avail": list(self.micro_mn_avail),
            "micro_fe_total": list(self.micro_fe_total),
            "micro_zn_total": list(self.micro_zn_total),
            "micro_mn_total": list(self.micro_mn_total),
            "agg_micro": list(self.agg_micro),
            "agg_meso": list(self.agg_meso),
            "agg_macro": list(self.agg_macro),
            "pore_network": dict(self.pore_network),
            "biopore": dict(self.biopore),
            "gas_diffusion": dict(self.gas_diffusion),
            "water_theta_macro": list(self.water_theta_macro),
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
            redox_eh=list(data.get("redox_eh", [])),
            micro_fe_avail=list(data.get("micro_fe_avail", [])),
            micro_zn_avail=list(data.get("micro_zn_avail", [])),
            micro_mn_avail=list(data.get("micro_mn_avail", [])),
            micro_fe_total=list(data.get("micro_fe_total", [])),
            micro_zn_total=list(data.get("micro_zn_total", [])),
            micro_mn_total=list(data.get("micro_mn_total", [])),
            agg_micro=list(data.get("agg_micro", [])),
            agg_meso=list(data.get("agg_meso", [])),
            agg_macro=list(data.get("agg_macro", [])),
            pore_network=dict(data.get("pore_network") or {}),
            biopore=dict(data.get("biopore") or {}),
            gas_diffusion=dict(data.get("gas_diffusion") or {}),
            water_theta_macro=list(data.get("water_theta_macro") or []),
        )


def _default_phen_params() -> CropPhenologyParams:
    return CropPhenologyParams(
        base_temperature_c=8.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )


def _plant_n_params(crop: CropPreset | None) -> PlantNitrogenParams:
    """Build whole-shoot critical-N params from a crop preset (#360).

    Uses the crop's fitted dilution coefficients when present (maize, wheat);
    otherwise falls back to PlantNitrogenParams' documented generic-C3 default
    (Greenwood et al. 1990).
    """
    if crop is None:
        return PlantNitrogenParams()
    overrides: dict[str, float] = {}
    if crop.n_crit_a is not None:
        overrides["n_crit_a"] = crop.n_crit_a
    if crop.n_crit_b is not None:
        overrides["n_crit_b"] = crop.n_crit_b
    return PlantNitrogenParams(**overrides)


def _default_canopy_params() -> CanopyParams:
    return CanopyParams(
        extinction_coefficient_k=0.6,
        radiation_use_efficiency_g_per_mj=3.0,
        specific_leaf_area_m2_per_g=0.02,
        lai_max=6.0,
        senescence_rate_per_day=0.01,
    )


# A subscription-plan factory: a zero-arg callable that constructs (and thereby
# subscribes) one runtime, or performs one bookkeeping subscription. The return
# value is discarded — the side effect is the subscription (#323).
_RuntimeFactory = Callable[[], object]


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
        # Pending above-ground biomass increment awaiting shoot→root
        # allocation (#330). Accumulated as canopy emits BiomassAccumulated,
        # drained by RootsRuntime on the plant_structure phase.
        self._pending_root_canopy_inc_g_m2: float = 0.0

        # Soil profile plus crop/atmosphere config that survives a
        # ``reset_crop`` (the ET model is crop-independent and stateless
        # across seasons; the per-day CO₂ buffer is orchestrator-owned per
        # ADR-010). Everything else is built through the shared factories.
        self.profile = profile
        # ET model (emits transpiration/evaporation related events via water
        # model). Built once; reset_crop reuses it.
        self.et = Evapotranspiration(et_params or EtParams())
        # Per-day CO₂ buffer used by GasDiffusion as the previous-day
        # respiration source term (#284). SOM emits ``CO2Respired`` on
        # the ``nutrients`` phase; gas diffusion reads + resets this
        # list on the following day's ``day_start`` phase.
        self._co2_buffer: list[float] = [0.0] * len(profile.layers)

        # Build the module/state graph through the shared factories so
        # ``__init__`` and ``reset_crop`` construct an identical graph and
        # subscription order (#323). The fresh-build path also creates the
        # state containers and computes the initial pore distribution.
        self._build_plant_modules(crop)
        self._build_soil_state()
        self._build_soil_modules()
        self._build_pore_state()
        self._build_pore_chain()
        # Compute the initial pore distribution so first-day reads see
        # populated values (the runtime re-derives it each tick). Only the
        # fresh-build path needs this; reset_crop restores saved pore state.
        self.pore_module.compute(profile, self.agg_state)

        self._wire_runtimes()

    # ------------------------------------------------------------------
    # Module factories — shared by __init__ and reset_crop (#323)
    # ------------------------------------------------------------------
    def _build_plant_modules(self, crop: CropPreset | None) -> None:
        """Construct the plant modules (phenology, canopy, roots).

        Falls back to defaults when no crop preset is supplied (a bare
        ``__init__`` with ``crop=None``); ``reset_crop`` always passes a
        preset. Shared so both paths build an identical plant graph.
        """
        phen_params = crop.phenology if crop else _default_phen_params()
        canopy_params = crop.canopy if crop else _default_canopy_params()
        root_params = crop.roots if crop else RootParams()
        self.phenology = PhenologyModule(phen_params, event_bus=self.event_bus)
        self.canopy = CanopyModule(canopy_params, event_bus=self.event_bus)
        self.roots = RootModule(root_params, event_bus=self.event_bus)
        self.root_state = RootState()
        # Whole-shoot plant-N accounting (#360). Fresh stock each season —
        # intentionally non-persisted (see SoilSnapshot docstring): a new
        # crop starts with ~0 shoot N.
        self.plant_n_module = PlantNitrogenModule(_plant_n_params(crop))
        self.plant_n_state = PlantNitrogenState()

    def _build_soil_state(self) -> None:
        """Create fresh mutable soil-state containers.

        Fresh-build only: ``reset_crop`` preserves the existing state
        objects and repopulates their pools from a snapshot, so it does not
        call this. State objects do not subscribe to the bus, so their
        creation order is irrelevant to dispatch order.
        """
        profile = self.profile
        n_layers = len(profile.layers)
        self.water_state = SoilWaterState(profile)
        self.n_state = SoilNitrogenState(profile)
        self.p_state = SoilPhosphorusState(profile)
        # Redox dynamics — Eh computation, CH4 production (AGRO-73)
        self.redox_state = RedoxState.from_layers(n_layers)
        # Micronutrients — Fe, Zn, Mn pH-dependent availability (AGRO-214)
        self.micro_state = MicronutrientState.from_profile(profile)
        # Soil aggregation — aggregate size distribution (AGRO-218)
        self.agg_state = SoilAggregationState.from_layers(n_layers)

    def _build_soil_modules(self) -> None:
        """Construct soil modules/cycles that subscribe to the event bus.

        Rebuilt by both ``__init__`` and ``reset_crop`` (the latter after
        ``event_bus.clear()``), always referencing the current soil-state
        objects. Construction order is load-bearing: several modules
        subscribe on construction and the bus dispatches in subscription
        order, so this sequence is part of the ADR-010 ordering contract
        (e.g. NitrogenCycle before PhosphorusCycle for ``WaterDrained``).
        """
        profile = self.profile
        n_layers = len(profile.layers)
        self.water_model = CascadingBucketWaterModel(event_bus=self.event_bus)
        # SOM is the authoritative N-mineralisation source in the full sim
        # (#351): disable the cycle's own organic-N mineralisation so organic
        # matter is not mineralised twice (once here, once by the SOM RothC
        # module via SOMDecomposed). See NitrogenRateParams docstring.
        self.n_cycle = NitrogenCycle(
            self.event_bus,
            self.n_state,
            water_state=self.water_state,
            profile=profile,
            params=NitrogenRateParams(enable_self_mineralization=False),
        )
        self.p_cycle = PhosphorusCycle(
            self.event_bus,
            self.p_state,
            water_state=self.water_state,
            profile=profile,
        )
        # Microbial biomass/enzymes (initial scaffold)
        self.microbes = MicrobialBiomassModule(
            MicrobialParams(n_layers=n_layers), event_bus=self.event_bus
        )
        # Chemistry emits pH events used by N/P
        self.chem = SoilChemistryModule(self.event_bus, n_layers=n_layers)
        self.redox = RedoxModule(
            RedoxParams(), self.redox_state, event_bus=self.event_bus
        )
        self.micro_cycle = MicronutrientCycle(
            self.event_bus, self.micro_state, MicronutrientParams(), n_layers
        )
        self.agg_module = AggregationModule(
            SoilAggregationParams(), self.agg_state, event_bus=self.event_bus
        )
        # Calendar for phased daily progression (emits DayTick; no
        # subscription, so its construction position is irrelevant).
        self.calendar = Calendar(self.event_bus)

    def _build_pore_state(self) -> None:
        """Create fresh pore-chain state containers (#284).

        Fresh-build only: ``reset_crop`` repopulates pore/biopore/gas state
        from a snapshot after rebuilding the modules.
        """
        n_layers = len(self.profile.layers)
        self.pore_state = PoreNetworkState.empty(n_layers)
        self.biopore_state = BioporeState.from_layers(n_layers)
        self.gas_state = GasDiffusionState.from_layers(n_layers)

    def _build_pore_chain(self) -> None:
        """Construct the pore-network → biopore → gas-diffusion modules (#284).

        The three modules only *emit* events; their runtimes (wired in
        :meth:`_wire_runtimes`) hold the subscriptions. So construction
        order here does not affect dispatch order — the ADR-010 day_start
        ordering is enforced by the subscription plan, not by this method.
        """
        self.pore_module = PoreNetworkModule(
            PoreNetworkParams(), self.pore_state, event_bus=self.event_bus
        )
        self.biopore_module = BioporeModule(
            BioporeParams(), self.biopore_state, event_bus=self.event_bus
        )
        self.gas_module = GasDiffusionModule(
            GasDiffusionParams(), self.gas_state, event_bus=self.event_bus
        )

    # ------------------------------------------------------------------
    # Runtime subscription wiring (#323, ADR-010)
    # ------------------------------------------------------------------
    # Named subscription groups. ``PORE_CHAIN`` must precede ``CORE`` so its
    # runtimes dispatch first on ``DayTick(day_start)`` (ADR-010).
    _PORE_CHAIN_GROUP = "pore_chain"
    _CORE_GROUP = "core"
    _BOOKKEEPING_GROUP = "bookkeeping"

    def _wire_runtimes(self) -> None:
        """Subscribe all runtime listeners via an explicit, ordered plan.

        The bus dispatches handlers in subscription order, so the order in
        which runtimes are constructed here is load-bearing for
        ``DayTick(day_start)``: the pore-chain runtimes (#284, ADR-010) must
        register **first** so the pore geometry, biopore donations, and gas
        profile are refreshed before downstream consumers (water, redox, N)
        tick. That invariant is made structural by the named-group ordering
        of :meth:`_subscription_plan` and enforced by
        :meth:`_assert_pore_chain_registered_first`, rather than being
        implied by raw statement order.
        """
        plan = self._subscription_plan()
        self._assert_pore_chain_registered_first(plan)
        for _group_name, factories in plan:
            for factory in factories:
                factory()

    def _subscription_plan(self) -> list[tuple[str, list[_RuntimeFactory]]]:
        """Return the ordered runtime-subscription plan (#323, ADR-010).

        Each entry is a ``(group_name, factories)`` pair. Groups apply in
        list order and factories within a group in list order. The
        ``pore_chain`` group is first, encoding the ADR-010 day_start
        invariant structurally instead of by comment. Each factory is a
        zero-arg callable whose side effect is one subscription.
        """
        # The migrated soil/plant runtimes take the structural
        # SoilProfileView port (#310, ADR-008). The concrete Pydantic
        # SoilProfile structurally satisfies that port (covariant `layers`
        # property), so it flows in directly — no cast needed.
        pv: SoilProfileView = self.profile
        # Pore-chain runtimes — subscribe in this order on day_start:
        # pore-network compute → biopore donation → gas diffusion (ADR-010).
        pore_chain: list[_RuntimeFactory] = [
            lambda: PoreNetworkRuntime(
                self.event_bus,
                self.pore_module,
                pv,
                agg_state=self.agg_state,
                biopore_module=self.biopore_module,
            ),
            lambda: BioporesRuntime(
                self.event_bus,
                self.biopore_module,
                pv,
                pore_state=self.pore_state,
            ),
            lambda: GasDiffusionRuntime(
                self.event_bus,
                self.gas_module,
                pv,
                self.water_state,
                self.pore_state,
                co2_respiration_supplier=self._co2_respiration_for_gas,
            ),
        ]
        core: list[_RuntimeFactory] = [
            lambda: WaterRuntime(
                self.event_bus,
                self.water_model,
                pv,
                self.water_state,
                agg_state=self.agg_state,
            ),
            lambda: PhenologyRuntime(
                self.event_bus, self.phenology, latitude_deg=self.latitude_deg
            ),
            lambda: RootsRuntime(
                self.event_bus,
                self.roots,
                self.root_state,
                pv,
                self.phenology,
                agg_state=self.agg_state,
                canopy_increment_provider=self._consume_root_canopy_increment,
            ),
            self._make_et_runtime,
            lambda: RedoxRuntime(
                self.event_bus,
                self.redox,
                pv,
                self.water_state,
                gas_state=self.gas_state,
            ),
            lambda: NitrogenRuntime(
                self.event_bus, self.n_cycle, gas_state=self.gas_state
            ),
            # Consumes NitrogenRuntime's PlantNUptakeComputed and emits the
            # graded NNI-based N stress the canopy reads (#360). Registered
            # right after NitrogenRuntime so the stock is updated the same
            # nutrients-phase tick the uptake is resolved.
            lambda: PlantNitrogenRuntime(
                self.event_bus,
                self.plant_n_module,
                self.plant_n_state,
                shoot_biomass_provider=lambda: self.canopy.state.biomass_g_m2,
            ),
            lambda: MicronutrientRuntime(self.event_bus, self.micro_cycle),
            lambda: PhosphorusRuntime(self.event_bus, self.p_cycle),
            lambda: self._make_som_runtime(pv),
            lambda: MicrobesRuntime(
                self.event_bus,
                self.microbes,
                profile=pv,
                water_state=self.water_state,
                chemistry=self.chem,
            ),
            lambda: AggregationRuntime(
                self.event_bus, self.agg_module, pv, self.water_state
            ),
            lambda: CanopyRuntime(
                self.event_bus,
                self.canopy,
                root_allocation_fraction=self.roots.params.root_allocation_fraction,
            ),
        ]
        bookkeeping: list[_RuntimeFactory] = [
            self._subscribe_biomass_bookkeeping,
            self._subscribe_co2_bookkeeping,
        ]
        return [
            (self._PORE_CHAIN_GROUP, pore_chain),
            (self._CORE_GROUP, core),
            (self._BOOKKEEPING_GROUP, bookkeeping),
        ]

    @staticmethod
    def _assert_pore_chain_registered_first(
        plan: list[tuple[str, list[_RuntimeFactory]]],
    ) -> None:
        """Enforce the ADR-010 invariant on the subscription plan.

        The pore-chain group must register before the core group so its
        runtimes dispatch first on ``DayTick(day_start)``. Raising here turns
        a silently reordered/dropped subscription — which would corrupt the
        water/redox/N coupling with no exception — into a construction-time
        error.
        """
        group_order = [name for name, _ in plan]
        pore = FullSimulationOrchestrator._PORE_CHAIN_GROUP
        core = FullSimulationOrchestrator._CORE_GROUP
        if pore not in group_order:
            raise ValueError("subscription plan is missing the pore-chain group")
        if core not in group_order:
            raise ValueError("subscription plan is missing the core group")
        if group_order.index(pore) >= group_order.index(core):
            raise ValueError(
                "ADR-010 violation: pore-chain runtimes must register before "
                "core runtimes (pore geometry and gas profile must refresh "
                "before water/redox/N consume them)"
            )

    def _make_et_runtime(self) -> ETRuntime:
        """Construct the ET runtime, casting concrete objects to ports.

        ETRuntime's fields are ``ports.py`` Protocols (#300, ADR-008), so the
        concrete soil/plant objects need a ``cast`` for mypy at this
        boundary.
        """
        from typing import cast as _cast

        from agrogame.params.ports import (
            CanopyView as _ETCanopy,
            RootDistribution as _ETRoots,
            WaterActuator as _ETActuator,
            WaterProfile as _ETProfile,
            WaterState as _ETState,
        )

        return ETRuntime(
            event_bus=self.event_bus,
            et=self.et,
            profile=_cast(_ETProfile, self.profile),
            water_state=_cast(_ETState, self.water_state),
            water_model=_cast(_ETActuator, self.water_model),
            roots_state=_cast(_ETRoots, self.root_state),
            canopy=_cast(_ETCanopy, self.canopy),
            _evap_state=EtState(),
            _residue=ResidueState(cover_fraction=self.et.params.residue_cover_fraction),
        )

    def _make_som_runtime(self, profile_view: SoilProfileView) -> SOMRuntime:
        """Construct the SOM runtime and retain it for pool inspection."""
        self._som_runtime = SOMRuntime(
            self.event_bus,
            profile_view,
            self.water_state,
            self.chem,
            agg_state=self.agg_state,
        )
        return self._som_runtime

    def _subscribe_biomass_bookkeeping(self) -> None:
        """Track canopy biomass increments for dynamic N/P demand (#284)."""
        from agrogame.soil.canopy.events import BiomassAccumulated

        self.event_bus.subscribe(BiomassAccumulated, self._on_biomass_accumulated)

    def _subscribe_co2_bookkeeping(self) -> None:
        """Buffer per-layer CO₂ so GasDiffusion (#284) has a source term.

        Derived from yesterday's SOM decomposition; see ADR-010.
        """
        self.event_bus.subscribe(CO2Respired, self._on_co2_respired)

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

    @property
    def plant_n_nni(self) -> float:
        """Current whole-shoot N nutrition index (NNI); 1.0 = at critical N."""
        return self.plant_n_state.nni

    @property
    def plant_n_stock_kg_ha(self) -> float:
        """Current accumulated whole-shoot N stock (kg/ha)."""
        return self.plant_n_state.n_stock_kg_ha

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
            redox_eh=list(self.redox_state.eh_mv),
            micro_fe_avail=list(self.micro_state.fe_available),
            micro_zn_avail=list(self.micro_state.zn_available),
            micro_mn_avail=list(self.micro_state.mn_available),
            micro_fe_total=list(self.micro_state.fe_total),
            micro_zn_total=list(self.micro_state.zn_total),
            micro_mn_total=list(self.micro_state.mn_total),
            agg_micro=list(self.agg_state.micro),
            agg_meso=list(self.agg_state.meso),
            agg_macro=list(self.agg_state.macro),
            pore_network=self.pore_state.to_dict(),
            biopore=self.biopore_state.to_dict(),
            gas_diffusion=self.gas_state.to_dict(),
            water_theta_macro=list(getattr(self.water_state, "theta_macro", []) or []),
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
        if snapshot.redox_eh:
            self.redox_state.eh_mv = list(snapshot.redox_eh)
            # Re-derive dominant acceptor from restored Eh values
            for i, eh in enumerate(self.redox_state.eh_mv):
                if i < len(self.redox_state.dominant_acceptor):
                    self.redox_state.dominant_acceptor[i] = (
                        RedoxModule._classify_acceptor(eh)
                    )

        if snapshot.micro_fe_avail:
            self.micro_state.fe_available = list(snapshot.micro_fe_avail)
            self.micro_state.zn_available = list(snapshot.micro_zn_avail)
            self.micro_state.mn_available = list(snapshot.micro_mn_avail)
        if snapshot.micro_fe_total:
            self.micro_state.fe_total = list(snapshot.micro_fe_total)
            self.micro_state.zn_total = list(snapshot.micro_zn_total)
            self.micro_state.mn_total = list(snapshot.micro_mn_total)
        if snapshot.agg_micro:
            self.agg_state.micro = list(snapshot.agg_micro)
            self.agg_state.meso = list(snapshot.agg_meso)
            self.agg_state.macro = list(snapshot.agg_macro)

        # --- Pore-network chain (#284) — backward-compat: empty dicts
        # mean a pre-#284 save, in which case we leave the freshly
        # initialised state alone. Use the public ``set_state`` API
        # (copy-in-place) so existing references held by the runtimes
        # and ``self.pore_state`` / ``self.biopore_state`` /
        # ``self.gas_state`` remain valid post-restore.
        if snapshot.pore_network:
            self.pore_module.set_state(
                PoreNetworkState.from_dict(snapshot.pore_network)
            )
        if snapshot.biopore:
            self.biopore_module.set_state(BioporeState.from_dict(snapshot.biopore))
        if snapshot.gas_diffusion:
            self.gas_module.set_state(
                GasDiffusionState.from_dict(snapshot.gas_diffusion)
            )
        if snapshot.water_theta_macro and hasattr(self.water_state, "theta_macro"):
            self.water_state.theta_macro = list(snapshot.water_theta_macro)

    def harvest(self) -> SoilSnapshot:
        """Finalize current crop and return soil state for next season.

        Appends the current crop to history and applies any N fixation
        credit (legumes) to the soil organic N pool in the top layer, then
        clears ``_current_crop`` (#359) so the finalized crop is not left as a
        stale reference. A second ``harvest()`` before ``reset_crop()`` is then
        a no-op (no double history entry or N credit), and downstream reads
        (``_compute_nutrient_demand``) correctly see a bare patch.
        """
        if self._current_crop is not None:
            self.crop_history.append(self._current_crop.key or self._current_crop.name)
            # Legume N fixation credit — added to organic N for slow
            # release via mineralization (Peoples et al. 2009)
            credit = self._current_crop.n_fixation_credit_kg_ha
            if credit > 0.0:
                self.n_state.organic_n[0] += credit
            self._current_crop = None
        return self.snapshot_soil()

    def reset_crop(self, new_crop: CropPreset) -> None:
        """Reset plant state for a new crop, preserving soil state.

        Clears all event subscriptions and rebuilds the plant, soil and
        pore-chain modules through the same factories used by ``__init__``
        (#323), so both construction paths produce an identical module graph
        and subscription order. The soil/pore/biopore/gas *state* objects are
        preserved (not re-created) and repopulated from a snapshot, so all
        pools (water, N, P, chemistry, microbes, SOM, redox, aggregation and
        the pore chain) carry across the transition exactly as before.
        """
        self._current_crop = new_crop
        self._day_counter = 0
        self._last_biomass_inc_g_m2 = 0.0
        self._pending_root_canopy_inc_g_m2 = 0.0
        # Reset the per-day CO₂ buffer to its fresh-init state (#352). Without
        # this, day 1 of the new season would read the prior season's buffered
        # respiration into the gas-diffusion / SOM chain. Matches the __init__
        # initialisation: one zeroed entry per soil layer.
        self._co2_buffer = [0.0] * len(self.profile.layers)
        # Capture soil state before tearing down subscriptions.
        soil = self.snapshot_soil()

        # Clear all event subscriptions to avoid stale handlers.
        self.event_bus.clear()

        # Rebuild the module graph through the shared factories. State
        # containers are preserved (no _build_*_state calls); the modules
        # re-reference them. Restore then repopulates pools before wiring,
        # matching the original restore-before-wire ordering.
        self._build_plant_modules(new_crop)
        self._build_soil_modules()
        self._build_pore_chain()

        # Restore soil state (water, N, P, pore chain, …) into the
        # preserved state objects.
        self.restore_soil(soil)

        # Re-wire all runtime listeners (identical order to __init__).
        self._wire_runtimes()

    def _on_biomass_accumulated(self, ev: Any) -> None:
        shoot_inc = float(ev.increment_g_m2)
        root_inc = float(getattr(ev, "root_increment_g_m2", 0.0))
        # N/P demand tracks *total* new tissue (shoot + root): both draw
        # nutrients, and the sum equals the day's assimilate pool, so demand
        # magnitude is unchanged by the source–sink split (#337; DSSAT CERES /
        # APSIM N-demand from prior-day growth).
        self._last_biomass_inc_g_m2 = shoot_inc + root_inc
        # Below-ground share of the pool, drained by RootsRuntime (#337).
        self._pending_root_canopy_inc_g_m2 += root_inc

    def _consume_root_canopy_increment(self) -> float:
        """Return the pending below-ground assimilate share and reset it (#337).

        The canopy already partitioned the single finite pool into shoot and
        root shares; this returns the accumulated root share. Injected into
        RootsRuntime as its ``canopy_increment_provider`` port so the plant
        package needs no import of ``soil.canopy``.
        """
        inc = self._pending_root_canopy_inc_g_m2
        self._pending_root_canopy_inc_g_m2 = 0.0
        return inc

    def _on_co2_respired(self, ev: Any) -> None:
        """Accumulate per-layer CO₂ for the gas-diffusion supplier (#284)."""
        layer = int(ev.layer)
        while len(self._co2_buffer) <= layer:
            self._co2_buffer.append(0.0)
        self._co2_buffer[layer] += float(ev.co2_c_kg_ha)

    def _co2_respiration_for_gas(self, n: int) -> list[float]:
        """Return previous day's per-layer CO₂; reset buffer for today (#284).

        Called once per ``DayTick(day_start)`` by ``GasDiffusionRuntime``.
        Returns the buffer SOM filled during the previous day's
        ``nutrients`` phase, then zeros it so this day's SOM run
        accumulates fresh totals for tomorrow's read.
        """
        out = list(self._co2_buffer[:n])
        if len(out) < n:
            out += [0.0] * (n - len(out))
        self._co2_buffer = [0.0] * n
        return out

    def _compute_plant_p_demand(self) -> float:
        """Compute P demand from previous day's biomass increment.

        Demand = biomass_increment (g/m² → kg/ha) × tissue_conc × soil_fraction.
        The soil_fraction (0.5) accounts for the fact that only ~50% of the
        plant's requirement comes from same-day soil uptake; the rest is
        remobilized from older tissue (Ritchie et al. 1998, DSSAT CERES).
        Ref: DSSAT CERES (Jones et al. 2003); APSIM nutrient-demand algorithm.

        N no longer uses this biomass-increment formula — the stock-based
        critical-N deficit in :meth:`_compute_plant_n_demand` (#360) supersedes
        it. P keeps the increment formula.
        """
        crop = self._current_crop
        if crop is None:
            return 0.0
        # 1 g/m² = 10 kg/ha (10,000 m² per ha)
        inc_kg_ha = self._last_biomass_inc_g_m2 * 10.0
        # Only ~50% of theoretical P demand is taken from soil each day;
        # the rest comes from internal remobilization of older tissue.
        soil_fraction = 0.5
        p_demand = inc_kg_ha * crop.tissue_p_conc_kg_kg * soil_fraction
        # Small baseline for maintenance uptake when growth is minimal
        return max(p_demand, 0.01)

    def _compute_plant_n_demand(self) -> float:
        """Stock-based whole-shoot N demand for the critical-N model (#360).

        Deficit between the current shoot N stock and the critical-N target
        for the current shoot DM (see PlantNitrogenModule.demand_to_critical).
        This replaces the legacy same-day 0.5-remobilisation N demand: with a
        stock model the plant requests enough N to reach critical, so an
        N-rich soil lets the stock track the critical curve (NNI -> 1) while a
        poor soil holds it below. P demand keeps its own formula
        (``_compute_plant_p_demand``). Uptake stays soil-supply limited.
        """
        if self._current_crop is None:
            return 0.1
        demand = self.plant_n_module.demand_to_critical(
            self.canopy.state.biomass_g_m2,
            self.plant_n_state.n_stock_kg_ha,
        )
        return max(0.1, demand)

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
            elif ev.action == "tillage":
                self.apply_tillage(ev.params.get("intensity", 0.5))
            else:
                raise ValueError(
                    f"Unknown management action {ev.action!r}; "
                    f"choose from 'irrigate', 'fertilize', 'tillage'"
                )

        # Compute dynamic demand unless the caller explicitly provides values.
        # N uses the stock-based critical-N deficit (#360); P keeps the
        # biomass-increment formula.
        dyn_p = self._compute_plant_p_demand()
        dyn_n = self._compute_plant_n_demand()
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

    def apply_tillage(self, intensity: float = 0.5) -> None:
        """Apply tillage to soil, destroying macroaggregates.

        Args:
            intensity: Tillage intensity (0.0 = no-till, 1.0 = moldboard plow).
        """
        depths = [ly.depth_cm for ly in self.profile.layers]
        self.agg_module.apply_tillage(intensity, layer_depths_cm=depths)

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
