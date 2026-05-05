"""Public API for the soil water package.

Docs: https://github.com/gedejong/agrogame/blob/main/docs/water.md

This package re-exports the primary classes and events for ease of import:
`EventBus`, `CascadingBucketWaterModel`, `SoilWaterBalance`, `DailyDrivers`,
`SoilWaterState`, `WaterFluxes`, and the water events.
"""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.water.events import (
    EvaporationTaken,
    PreferentialFlowOccurred,
    RunoffGenerated,
    WaterDrained,
    WaterInfiltrated,
)
from agrogame.soil.water.legacy import SoilWaterBalance
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.models.dual_porosity import (
    DualPorosityParams,
    DualPorosityWaterModel,
    partition_flow,
)
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers, WaterFluxes

__all__ = [
    "EventBus",
    "WaterInfiltrated",
    "WaterDrained",
    "RunoffGenerated",
    "EvaporationTaken",
    "PreferentialFlowOccurred",
    "WaterFluxes",
    "DailyDrivers",
    "SoilWaterState",
    "CascadingBucketWaterModel",
    "DualPorosityParams",
    "DualPorosityWaterModel",
    "partition_flow",
    "SoilWaterBalance",
]
