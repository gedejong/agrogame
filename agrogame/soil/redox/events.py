"""Redox domain events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class RedoxChanged(BaseEvent):
    """Redox potential updated for a soil layer.

    Emitted once per layer per daily step.
    """

    layer: int
    eh_mv: float
    dominant_acceptor: str


@dataclass(frozen=True)
class N2OEmitted(BaseEvent):
    """Nitrous oxide emitted during denitrification.

    Attributes:
        layer: Soil layer index.
        amount_kg_n_ha: N2O-N emitted (kg N/ha).
        n2_amount_kg_n_ha: N2-N emitted (kg N/ha).
    """

    layer: int
    amount_kg_n_ha: float
    n2_amount_kg_n_ha: float


@dataclass(frozen=True)
class CH4Emitted(BaseEvent):
    """Methane produced under strongly reducing conditions.

    Attributes:
        layer: Soil layer index.
        amount_kg_c_ha: CH4-C produced (kg C/ha).
    """

    layer: int
    amount_kg_c_ha: float


@dataclass(frozen=True)
class CH4Oxidized(BaseEvent):
    """Methane oxidized in aerobic zone.

    Attributes:
        layer: Layer where oxidation occurred.
        amount_kg_c_ha: CH4-C oxidized (kg C/ha).
    """

    layer: int
    amount_kg_c_ha: float
