from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from agrogame.soil.phenology import PhenologyStage


@dataclass(frozen=True)
class RootParams:
    max_depth_cm: float = 120.0
    growth_rate_cm_per_day: float = 1.5
    distribution: str = "exponential"  # or "uniform"
    turnover_rate_per_day: float = 0.005
    proliferation_strength: float = 0.0  # 0 disables nutrient-driven bias
    stage_multipliers: Dict[PhenologyStage, float] | None = None
