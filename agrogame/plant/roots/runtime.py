from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.phenology import PhenologyModule
from .module import RootModule
from .types import RootState


@dataclass
class RootsRuntime:
    event_bus: EventBus
    module: RootModule
    state: RootState
    profile: SoilProfile
    phenology: PhenologyModule
    agg_state: object | None = None  # SoilAggregationState (optional)

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

            mwd_fn = getattr(self.agg_state, "mwd", None)
            if mwd_fn is not None:
                # Use surface MWD as representative constraint
                mwd = mwd_fn(0)
                constraints = {"agg_penetration": root_penetration_factor(mwd)}
        _ = self.module.daily_step(
            state=self.state,
            profile=self.profile,
            stage=self.phenology.state.stage,
            constraints=constraints,
        )
