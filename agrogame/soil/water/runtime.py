"""Runtime wiring for water model to respond to Calendar DayTick events.

Listens for the "water" phase and delegates to the configured water model's
`update_daily` using the provided `DailyDrivers`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.params.ports import SoilProfileView
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers

if TYPE_CHECKING:
    from agrogame.soil.aggregation.state import SoilAggregationState


@dataclass
class WaterRuntime:
    """Bind a water model to the event bus to run on the water phase."""

    event_bus: EventBus
    model: CascadingBucketWaterModel
    profile: SoilProfileView
    state: SoilWaterState
    agg_state: SoilAggregationState | None = None

    def __post_init__(self) -> None:
        """Subscribe to DayTick events on construction."""
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "water":
            return
        # Check waterlogging BEFORE daily water model runs — irrigation
        # applied before step_day may have saturated the soil.
        self._check_waterlogging()
        drivers = ev.drivers or DailyDrivers(
            rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
        )
        ksat_factors = None
        porosity_overrides = None
        if self.agg_state is not None:
            from agrogame.soil.aggregation.dynamic_state import (
                effective_ksat_factor,
                effective_porosity,
            )

            n = len(self.profile.layers)
            macro = self.agg_state.macro
            if len(macro) >= n:
                ksat_factors = [effective_ksat_factor(macro[i]) for i in range(n)]
                porosity_overrides = [
                    effective_porosity(self.profile.layers[i].saturation, macro[i])
                    for i in range(n)
                ]
        _ = self.model.update_daily(
            self.profile,
            self.state,
            drivers,
            ksat_factors=ksat_factors,
            porosity_overrides=porosity_overrides,
        )

    def _check_waterlogging(self) -> None:
        """Emit WaterloggingDetected if top-layer theta >= saturation."""
        if not self.profile.layers:
            return
        theta = self.state.theta[0]
        sat = self.profile.layers[0].saturation
        if theta >= sat * 0.95:  # near-saturation threshold
            from agrogame.soil.water.events import WaterloggingDetected

            self.event_bus.emit(
                WaterloggingDetected(layer=0, theta=theta, saturation=sat)
            )
