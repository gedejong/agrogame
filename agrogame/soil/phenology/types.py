from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PhenologyStage(Enum):
    PLANTED = "planted"
    EMERGED = "emerged"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    GRAIN_FILL = "grain_fill"
    MATURITY = "maturity"


@dataclass
class PhenologyState:
    accumulated_gdd: float
    stage: PhenologyStage
    vernalization_units: float = 0.0
