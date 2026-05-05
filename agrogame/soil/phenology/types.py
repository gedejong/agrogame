from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# PhenologyStage moved to agrogame.params.phenology (#300, ADR-008).
# Re-exported here so existing soil-internal callers keep working.
from agrogame.params.phenology import PhenologyStage

__all__ = ["PhenologyStage", "PhenologyState"]


@dataclass
class PhenologyState:
    """Mutable phenology state: accumulated GDD, current stage, vernalization units."""

    accumulated_gdd: float
    stage: PhenologyStage
    vernalization_units: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "accumulated_gdd": self.accumulated_gdd,
            "stage": self.stage.value,
            "vernalization_units": self.vernalization_units,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PhenologyState:
        gdd = float(data.get("accumulated_gdd", 0.0))
        vern = float(data.get("vernalization_units", 0.0))
        return cls(
            accumulated_gdd=gdd,
            stage=PhenologyStage(data.get("stage", "planted")),
            vernalization_units=vern,
        )
