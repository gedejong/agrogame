"""Shared phenology types — stages, thresholds, crop parameters.

Lives under ``agrogame.params`` (not ``agrogame.soil.phenology``) so that
the plant package can import these types without violating the
``plant_vs_soil`` and ``domain_layers`` import-linter contracts (#300,
ADR-008). The soil-side phenology runtime re-exports the same names for
back-compat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PhenologyStage(Enum):
    """Crop development stage, ordered from planting to maturity."""

    PLANTED = "planted"
    EMERGED = "emerged"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    GRAIN_FILL = "grain_fill"
    MATURITY = "maturity"


@dataclass(frozen=True)
class GrowthStageThresholds:
    """GDD thresholds that gate transitions between development stages."""

    emergence_gdd: float
    flowering_gdd: float
    maturity_gdd: float


@dataclass(frozen=True)
class CropPhenologyParams:
    """Frozen phenology params: GDD base/max, stages, photoperiod, vernalization."""

    base_temperature_c: float
    max_temperature_c: float
    thresholds: GrowthStageThresholds
    photoperiod_sensitivity: float | None = None  # 0..1 multiplier; None to disable
    vernalization_required_units: float | None = (
        None  # units needed to unlock flowering
    )
