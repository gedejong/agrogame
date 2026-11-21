from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.params.ports import SoilProfileView
from agrogame.soil.aggregation.dynamic_state import CALIBRATED_ROOT_ELONGATION_FACTOR
from agrogame.soil.phenology import PhenologyModule
from .module import RootModule
from .types import RootState


@dataclass
class RootsRuntime:
    """Wire RootModule to the EventBus; subscribes to DayTick to advance roots daily.

    ``canopy_increment_provider`` is an injected port (ADR-008) returning the
    below-ground share of the daily assimilate pool (g/m²) accumulated since
    the last root step, and resetting it on read. The canopy already partitions
    the single finite pool into shoot and root shares (Σ = 1, #337), so the
    value returned here is the root share directly — no partition fraction is
    re-applied. It decouples the root package from ``soil.canopy`` (which the
    ``plant_vs_soil`` import contract forbids importing): the orchestrator
    observes ``BiomassAccumulated`` and supplies the value.
    """

    event_bus: EventBus
    module: RootModule
    state: RootState
    profile: SoilProfileView
    phenology: PhenologyModule
    canopy_increment_provider: Callable[[], float] | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _daily_root_allocation(self) -> float:
        """Below-ground share of today's assimilate pool routed to roots.

        The canopy already reserved this share from the single finite pool
        (Σ shoot+root = 1, #337); the provider returns it directly, so no
        partition fraction is re-applied here.
        """
        if self.canopy_increment_provider is None:
            return 0.0
        return max(0.0, self.canopy_increment_provider())

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "plant_structure":
            return
        # Root elongation does not read aggregate structure (ADR-021, #526).
        # The constant preserves the calibration (the realism suite was
        # calibrated under this value on day 0) and is not a soil-strength
        # parameter. Tillage must not tighten rooting (Lampurlanés &
        # Cantero-Martínez 2003, Agron. J. 95:526-536,
        # doi:10.2134/agronj2003.5260; Grant & Lafond 1993, Can. J. Soil
        # Sci. 73:223-232, doi:10.4141/cjss93-024), and the CERES-Maize and
        # APSIM root fronts have no aggregate term. See
        # docs/adr/ADR-021-root-elongation-aggregate-coupling.md.
        constraints = {"agg_penetration": CALIBRATED_ROOT_ELONGATION_FACTOR}
        _ = self.module.daily_step(
            state=self.state,
            profile=self.profile,
            stage=self.phenology.state.stage,
            daily_root_biomass_g_m2=self._daily_root_allocation(),
            constraints=constraints,
        )
