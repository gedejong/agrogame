"""Biopore domain events (#215)."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class BioporeCreated(BaseEvent):
    """Biopores created in a soil layer from root channels.

    Attributes:
        layer: Soil layer index.
        density_delta: Increase in biopore count per m².
        volume_delta: Increase in biopore volume fraction (m³/m³).
    """

    layer: int
    density_delta: float
    volume_delta: float


@dataclass(frozen=True)
class BioporeCollapsed(BaseEvent):
    """Biopores destroyed by tillage or compaction.

    Attributes:
        layer: Soil layer index.
        cause: One of "tillage", "compaction", "decay".
        density_lost: Number of biopores destroyed per m².
    """

    layer: int
    cause: str
    density_lost: float
