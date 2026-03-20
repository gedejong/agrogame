"""Nitrogen domain events emitted by the nitrogen module."""

from __future__ import annotations

from dataclasses import dataclass
from agrogame.events import BaseEvent


@dataclass(frozen=True)
class NutrientLeached(BaseEvent):
    """Nutrient mass lost from the profile with drainage.

    Attributes:
        nutrient: Nutrient identifier (e.g., 'NO3', 'NH4').
        amount_kg_ha: Mass leached (kg/ha).
        layer: Zero-based layer index where leaching originated.
    """

    nutrient: str
    amount_kg_ha: float
    layer: int


@dataclass(frozen=True)
class NitrificationOccurred(BaseEvent):
    """Nitrification transformation diagnostic for a layer on a given day.

    Attributes:
        layer: Zero-based layer index.
        amount_kg_ha: Mass of N converted from NH4 to NO3 (kg/ha).
    """

    layer: int
    amount_kg_ha: float
