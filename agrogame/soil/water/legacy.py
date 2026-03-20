"""Legacy compatibility wrapper for the previous `SoilWaterBalance` API."""

from __future__ import annotations

from typing import Tuple

from agrogame.soil.models import SoilProfile
from agrogame.events import EventBus
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.canopy.interception import InterceptionState
from agrogame.soil.water.events import CanopyIntercepted, CanopyEvaporated


class SoilWaterBalance:
    """Wrapper maintaining the historical tuple-returning API.

    Stores `last_*` properties for evaporation, runoff, and deep drainage to
    ease migration of existing callers.
    """

    def __init__(
        self,
        profile: SoilProfile,
        event_bus: EventBus | None = None,
        interception: InterceptionState | None = None,
    ):
        """Create the balance wrapper for a given profile.

        Args:
            profile: Static soil profile definition.
            event_bus: Optional bus to emit water events on.
            interception: Optional interception state to enable canopy storage
                and canopy-priority evaporation during daily updates.
        """
        self.profile = profile
        self._state = SoilWaterState(profile)
        self._bus = event_bus
        self._model = CascadingBucketWaterModel(event_bus=event_bus)
        self._interception = interception
        self.last_runoff_mm: float = 0.0
        self.last_deep_drainage_mm: float = 0.0
        self.last_evap_mm: float = 0.0
        self.last_canopy_evap_mm: float = 0.0
        self.last_intercepted_mm: float = 0.0

    def update_daily(
        self,
        rainfall_mm: float,
        irrigation_mm: float = 0.0,
        evaporation_mm: float = 0.0,
        *,
        lai: float | None = None,
    ) -> Tuple[float, float, float]:
        """Advance one day and return (runoff, deep_drainage, storage_change)."""
        rain_in = max(0.0, rainfall_mm)
        pot_evap = max(0.0, evaporation_mm)

        throughfall = rain_in
        canopy_evap = 0.0
        intercepted = 0.0
        # If interception enabled and LAI provided, apply interception and
        # canopy evaporation
        if self._interception is not None and lai is not None and lai > 0.0:
            intercepted, throughfall = self._interception.intercept(lai, rain_in)
            if self._bus is not None and intercepted > 0.0:
                self._bus.emit(CanopyIntercepted(amount_mm=intercepted))
            canopy_evap = self._interception.evaporate(pot_evap)
            if self._bus is not None and canopy_evap > 0.0:
                self._bus.emit(CanopyEvaporated(amount_mm=canopy_evap))
            pot_evap = max(0.0, pot_evap - canopy_evap)

        flux = self._model.update_daily(
            self.profile,
            self._state,
            DailyDrivers(
                rainfall_mm=throughfall,
                irrigation_mm=irrigation_mm,
                evaporation_mm=pot_evap,
            ),
        )
        self.last_runoff_mm = flux.runoff_mm
        self.last_deep_drainage_mm = flux.deep_drainage_mm
        self.last_canopy_evap_mm = canopy_evap
        self.last_intercepted_mm = intercepted
        # Aggregate canopy + soil evaporation for accounting convenience
        self.last_evap_mm = canopy_evap + flux.evap_mm
        return flux.runoff_mm, flux.deep_drainage_mm, flux.storage_change_mm
