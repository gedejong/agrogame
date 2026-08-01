"""Sulfur domain events emitted by the sulfur module."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class SulfurMineralized(BaseEvent):
    """Event emitted when organic S is mineralized to plant-available SO4.

    Attributes:
        layer: Zero-based layer index where mineralization occurred.
        amount_kg_ha: Mass of S mineralized (kg/ha).
    """

    layer: int
    amount_kg_ha: float


@dataclass(frozen=True)
class SulfurAdsorbed(BaseEvent):
    """Event emitted when SO4 net-adsorbs onto (or desorbs from) soil surfaces.

    Attributes:
        layer: Zero-based layer index where the exchange occurred.
        amount_kg_ha: Net S moved from the available into the adsorbed pool
            (kg/ha); negative under net desorption.
    """

    layer: int
    amount_kg_ha: float
