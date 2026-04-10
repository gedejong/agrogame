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


@dataclass(frozen=True)
class NutrientStressComputed(BaseEvent):
    """Nutrient stress signals computed from uptake vs demand proxies.

    Attributes:
        nutrient: "N", "P", "Fe", "Zn", or "Mn".
        uptake_kg_ha: Actual plant uptake (kg/ha) during the day.
        demand_kg_ha: Plant demand (kg/ha) requested for the day.
        stress: Computed stress factor in 0..1 (uptake/demand clamped).
    """

    nutrient: str
    uptake_kg_ha: float
    demand_kg_ha: float
    stress: float
