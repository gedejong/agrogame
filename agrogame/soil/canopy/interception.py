from __future__ import annotations

from dataclasses import dataclass
from agrogame.events import EventBus
from .events import CanopyIntercepted, CanopyEvaporated


@dataclass
class InterceptionState:
    """Simple canopy rainfall interception store.

    capacity_coef_mm_per_lai: interception capacity per unit LAI (mm/LAI).
    store_mm: current intercepted water stored on the canopy (mm).
    """

    capacity_coef_mm_per_lai: float = 0.2
    store_mm: float = 0.0
    event_bus: EventBus | None = None

    def capacity_mm(self, lai: float) -> float:
        return max(0.0, self.capacity_coef_mm_per_lai * max(0.0, lai))

    def intercept(self, lai: float, rainfall_mm: float) -> tuple[float, float]:
        """Intercept rainfall up to remaining capacity.

        Returns (intercepted_mm, throughfall_mm).
        """
        incoming = max(0.0, rainfall_mm)
        cap = self.capacity_mm(lai)
        room = max(0.0, cap - self.store_mm)
        take = min(room, incoming)
        self.store_mm += take
        if self.event_bus is not None and take > 0.0:
            self.event_bus.emit(CanopyIntercepted(amount_mm=take))
        return take, incoming - take

    def evaporate(self, potential_evap_mm: float) -> float:
        """Evaporate from the canopy store, prioritized before soil.

        Returns the amount taken from the canopy (mm).
        """
        if potential_evap_mm <= 0.0 or self.store_mm <= 0.0:
            return 0.0
        take = min(self.store_mm, potential_evap_mm)
        self.store_mm -= take
        if self.event_bus is not None and take > 0.0:
            self.event_bus.emit(CanopyEvaporated(amount_mm=take))
        return take
