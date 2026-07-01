"""Deprecated: ET Protocol ports moved to ``agrogame.params.ports`` (#310).

This module now re-exports the ports from their new shared home so existing
imports keep working during migration. Prefer importing from
``agrogame.params.ports`` directly.
"""

from __future__ import annotations

from agrogame.params.ports import (
    CanopyView,
    EvaporationApplier,
    RootDistribution,
    SoilLayer,
    TranspirationExtractor,
    WaterActuator,
    WaterProfile,
    WaterState,
)

__all__ = [
    "CanopyView",
    "EvaporationApplier",
    "RootDistribution",
    "SoilLayer",
    "TranspirationExtractor",
    "WaterActuator",
    "WaterProfile",
    "WaterState",
]
