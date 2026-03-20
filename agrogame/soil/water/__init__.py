"""Public API for the soil water package.

This package re-exports the primary classes and events for ease of import:
`EventBus`, `CascadingBucketWaterModel`, `SoilWaterBalance`, `DailyDrivers`,
`SoilWaterState`, `WaterFluxes`, and the water events.
"""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.water.events import (
    EvaporationTaken,
    RunoffGenerated,
    WaterDrained,
    WaterInfiltrated,
)
from agrogame.soil.water.legacy import SoilWaterBalance
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers, WaterFluxes

__all__ = [
    "EventBus",
    "WaterInfiltrated",
    "WaterDrained",
    "RunoffGenerated",
    "EvaporationTaken",
    "WaterFluxes",
    "DailyDrivers",
    "SoilWaterState",
    "CascadingBucketWaterModel",
    "SoilWaterBalance",
]
