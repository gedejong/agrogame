from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class WaterStressComputed(BaseEvent):
    """Water stress signal computed from ET supply/demand.

    Attributes:
        supply_mm: Actual transpiration supplied (mm).
        demand_mm: Potential transpiration demand (mm).
        stress: Computed stress factor in 0..1 (supply/demand clamped).
    """

    supply_mm: float
    demand_mm: float
    stress: float
