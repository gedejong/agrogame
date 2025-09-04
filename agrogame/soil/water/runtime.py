"""Runtime wiring for water model to respond to Calendar DayTick events.

Listens for the "water" phase and delegates to the configured water model's
`update_daily` using the provided `DailyDrivers`.
"""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers


@dataclass
class WaterRuntime:
    """Bind a water model to the event bus to run on the water phase."""

    event_bus: EventBus
    model: CascadingBucketWaterModel
    profile: SoilProfile
    state: SoilWaterState

    def __post_init__(self) -> None:
        """Subscribe to DayTick events on construction."""
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "water":
            return
        drivers = ev.drivers or DailyDrivers(
            rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
        )
        _ = self.model.update_daily(self.profile, self.state, drivers)
