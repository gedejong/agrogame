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
class PlantNUptakeComputed(BaseEvent):
    """Daily soil N uptake handed off to whole-shoot plant-N accounting (#360).

    Emitted by the nitrogen runtime on the ``nutrients`` phase, once soil N
    uptake has been resolved (mass-flow limited, unchanged). The plant-N
    runtime consumes it to grow the whole-shoot N stock and derive the graded
    NNI-based stress. This decouples the soil-side uptake from the plant-side
    critical-N model without the soil layer importing plant logic.

    Attributes:
        uptake_kg_ha: N taken up from the soil this day (kg/ha).
        demand_kg_ha: N demand requested for the day (kg/ha), passed through
            for diagnostics and the downstream stress event.
    """

    uptake_kg_ha: float
    demand_kg_ha: float


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
