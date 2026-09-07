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


@dataclass(frozen=True)
class MineralizationOccurred(BaseEvent):
    """Mineralization diagnostic: organic N converted to NH4."""

    layer: int
    amount_kg_ha: float


@dataclass(frozen=True)
class DenitrificationOccurred(BaseEvent):
    """Denitrification diagnostic: NO3 lost as gas under anaerobic conditions."""

    layer: int
    amount_kg_ha: float


@dataclass(frozen=True)
class VolatilizationOccurred(BaseEvent):
    """Volatilization diagnostic: NH3 loss from surface NH4."""

    layer: int
    amount_kg_ha: float


@dataclass(frozen=True)
class MassFlowNSupplyComputed(BaseEvent):
    """Potential nitrate supply to roots by transpiration mass flow.

    A diagnostic only: plant uptake is demand-driven and availability-capped,
    so this supply is neither debited from the soil nor credited to the plant.

    Attributes:
        total_kg_ha: Whole-profile potential NO3 supply for the day (kg/ha).
        by_layer: Per-layer potential supply (kg/ha), one entry per soil layer.
    """

    total_kg_ha: float
    by_layer: tuple[float, ...]
