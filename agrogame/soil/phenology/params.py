from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GrowthStageThresholds:
    emergence_gdd: float
    flowering_gdd: float
    maturity_gdd: float


@dataclass(frozen=True)
class CropPhenologyParams:
    base_temperature_c: float
    max_temperature_c: float
    thresholds: GrowthStageThresholds
    # Optional photoperiod sensitivity could be added later
