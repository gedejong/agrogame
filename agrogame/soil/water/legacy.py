"""Legacy compatibility wrapper for the previous `SoilWaterBalance` API."""

from __future__ import annotations

from typing import Tuple

from agrogame.soil.models import SoilProfile
from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers


class SoilWaterBalance:
    """Wrapper maintaining the historical tuple-returning API.

    Stores `last_*` properties for evaporation, runoff, and deep drainage to
    ease migration of existing callers.
    """

    def __init__(self, profile: SoilProfile, event_bus: EventBus | None = None):
        """Create the balance wrapper for a given profile.

        Args:
            profile: Static soil profile definition.
            event_bus: Optional bus to emit water events on.
        """
        self.profile = profile
        self._state = SoilWaterState(profile)
        self._model = CascadingBucketWaterModel(event_bus=event_bus)
        self.last_runoff_mm: float = 0.0
        self.last_deep_drainage_mm: float = 0.0
        self.last_evap_mm: float = 0.0

    def update_daily(
        self,
        rainfall_mm: float,
        irrigation_mm: float = 0.0,
        evaporation_mm: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Advance one day and return (runoff, deep_drainage, storage_change)."""
        flux = self._model.update_daily(
            self.profile,
            self._state,
            DailyDrivers(
                rainfall_mm=rainfall_mm,
                irrigation_mm=irrigation_mm,
                evaporation_mm=evaporation_mm,
            ),
        )
        self.last_runoff_mm = flux.runoff_mm
        self.last_deep_drainage_mm = flux.deep_drainage_mm
        self.last_evap_mm = flux.evap_mm
        return flux.runoff_mm, flux.deep_drainage_mm, flux.storage_change_mm
