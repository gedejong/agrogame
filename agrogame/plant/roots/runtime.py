from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.params.ports import SoilProfileView
from agrogame.soil.phenology import PhenologyModule
from .module import RootModule
from .types import RootState

if TYPE_CHECKING:
    from agrogame.soil.aggregation.state import SoilAggregationState


@dataclass
class RootsRuntime:
    """Wire RootModule to the EventBus; subscribes to DayTick to advance roots daily.

    ``canopy_increment_provider`` is an injected port (ADR-008) returning the
    pending above-ground biomass increment (g/m²) accumulated since the last
    root step, and resetting it on read. It decouples the root package from
    ``soil.canopy`` (which the ``plant_vs_soil`` import contract forbids
    importing): the orchestrator observes ``BiomassAccumulated`` and supplies
    the value. A crop-parameterised fraction of it is allocated to root
    biomass each day.
    """

    event_bus: EventBus
    module: RootModule
    state: RootState
    profile: SoilProfileView
    phenology: PhenologyModule
    agg_state: SoilAggregationState | None = None
    canopy_increment_provider: Callable[[], float] | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _daily_root_allocation(self) -> float:
        """Fraction of the pending canopy biomass increment routed to roots."""
        if self.canopy_increment_provider is None:
            return 0.0
        canopy_inc = max(0.0, self.canopy_increment_provider())
        return self.module.params.root_allocation_fraction * canopy_inc

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "plant_structure":
            return
        constraints: dict | None = None
        if self.agg_state is not None:
            from agrogame.soil.aggregation.dynamic_state import (
                root_penetration_factor,
            )

            # TODO: per-layer MWD constraint for depth-dependent resistance
            mwd = self.agg_state.mwd(0)
            constraints = {"agg_penetration": root_penetration_factor(mwd)}
        _ = self.module.daily_step(
            state=self.state,
            profile=self.profile,
            stage=self.phenology.state.stage,
            daily_root_biomass_g_m2=self._daily_root_allocation(),
            constraints=constraints,
        )
