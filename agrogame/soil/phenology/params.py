from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GrowthStageThresholds:
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
