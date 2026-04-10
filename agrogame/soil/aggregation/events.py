"""Soil aggregation domain events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class AggregateStructureUpdated(BaseEvent):
    """Aggregate size distribution updated for a soil layer.

    Emitted after weekly aggregation step.
    """

    layer: int
    micro: float
    meso: float
    macro: float
    mwd_mm: float


@dataclass(frozen=True)
class TillageApplied(BaseEvent):
    """Tillage disturbance applied to the soil.

    Attributes:
        intensity: Tillage intensity (0.0–1.0).
        macro_destroyed_frac: Fraction of macroaggregates destroyed.
    """

    intensity: float
    macro_destroyed_frac: float


@dataclass(frozen=True)
class StructureDegraded(BaseEvent):
    """Aggregate structure degraded by physical disruption.

    Emitted when wet-dry, freeze-thaw, or raindrop impact breaks
    macroaggregates.

    Attributes:
        layer: Soil layer index.
        cause: One of "wet_dry", "freeze_thaw", "raindrop".
        macro_lost_frac: Fraction of macro broken down.
    """

    layer: int
    cause: str
    macro_lost_frac: float
