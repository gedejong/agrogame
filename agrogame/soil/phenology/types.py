from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PhenologyStage(str, Enum):
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
