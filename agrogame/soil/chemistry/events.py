"""Soil chemistry events (e.g., pH updates)."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class SoilPHUpdated(BaseEvent):
    """Event emitted when soil pH for a layer is updated.

    Attributes:
        layer: Zero-based layer index.
        ph: New pH value for the layer.
    """

    layer: int
    ph: float


@dataclass(frozen=True)
class LimeApplied(BaseEvent):
    """Application of lime to a soil layer (raises pH).

    Attributes:
        layer: Zero-based layer index.
        rate_kg_ha: Lime rate (kg/ha as CaCO3-equivalent).
    """

    layer: int
    rate_kg_ha: float
