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

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "plant_structure":
            return
        _ = self.module.daily_step(
            state=self.state,
            profile=self.profile,
            stage=self.phenology.state.stage,
        )
