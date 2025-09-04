"""Phosphorus domain events emitted by the phosphorus module."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class PhosphorusFixationOccurred(BaseEvent):
    """Event emitted when available P is fixed into unavailable forms.

    Attributes:
        layer: Zero-based layer index where fixation occurred.
        amount_fixed_kg_ha: Amount of P fixed (kg/ha).
    """

    layer: int
    amount_fixed_kg_ha: float
