"""Back-compat shim — phenology params live at agrogame.params.phenology (#300)."""

from __future__ import annotations

from agrogame.params.phenology import CropPhenologyParams, GrowthStageThresholds

__all__ = ["CropPhenologyParams", "GrowthStageThresholds"]
