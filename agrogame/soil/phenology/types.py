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

    def to_dict(self) -> dict[str, object]:
        return {
            "accumulated_gdd": self.accumulated_gdd,
            "stage": self.stage.value,
            "vernalization_units": self.vernalization_units,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> PhenologyState:
        gdd = float(data.get("accumulated_gdd", 0.0))  # type: ignore[arg-type]
        vern = float(data.get("vernalization_units", 0.0))  # type: ignore[arg-type]
        return cls(
            accumulated_gdd=gdd,
            stage=PhenologyStage(data.get("stage", "planted")),
            vernalization_units=vern,
        )
