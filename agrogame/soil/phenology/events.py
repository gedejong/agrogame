from __future__ import annotations

from dataclasses import dataclass

from .types import PhenologyStage


@dataclass(frozen=True)
class GddAccumulated:
    """Daily GDD increment and new total accumulated thermal time."""

    daily_gdd: float
    total_gdd: float


@dataclass(frozen=True)
class StageChanged:
    """Phenological stage transition event."""

    from_stage: PhenologyStage
    to_stage: PhenologyStage
    at_gdd: float
