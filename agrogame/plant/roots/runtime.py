from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.phenology import PhenologyModule
from .module import RootModule
from .types import RootState

if TYPE_CHECKING:
    from agrogame.soil.aggregation.state import SoilAggregationState


@dataclass
class RootsRuntime:
    """Wire RootModule to the EventBus; subscribes to DayTick to advance roots daily."""

    event_bus: EventBus
    module: RootModule
    state: RootState
    profile: SoilProfile
    phenology: PhenologyModule
    agg_state: SoilAggregationState | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

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
            constraints=constraints,
        )
