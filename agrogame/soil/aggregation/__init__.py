"""Soil aggregation — aggregate size distribution and stability."""

from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.aggregation.params import SoilAggregationParams
from agrogame.soil.aggregation.module import AggregationModule
from agrogame.soil.aggregation.events import (
    AggregateStructureUpdated,
    TillageApplied,
    StructureDegraded,
)

__all__ = [
    "SoilAggregationState",
    "SoilAggregationParams",
    "AggregationModule",
    "AggregateStructureUpdated",
    "TillageApplied",
    "StructureDegraded",
]
