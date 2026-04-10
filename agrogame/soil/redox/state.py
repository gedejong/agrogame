"""Mutable redox state per soil layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DominantAcceptor(Enum):
    """Dominant electron acceptor in the redox ladder."""

    OXYGEN = "O2"
    NITRATE = "NO3"
    IRON = "Fe3+"
    METHANOGENESIS = "CH4"


@dataclass
class RedoxState:
    """Per-layer redox potential and dominant acceptor.

    Attributes:
        eh_mv: Redox potential per layer (mV). Positive = oxidizing.
        dominant_acceptor: Current dominant electron acceptor per layer.
    """

    eh_mv: list[float] = field(default_factory=list)
    dominant_acceptor: list[DominantAcceptor] = field(default_factory=list)

    @staticmethod
    def from_layers(n_layers: int) -> RedoxState:
        """Initialize with aerobic conditions (Eh = +400 mV)."""
        return RedoxState(
            eh_mv=[400.0] * n_layers,
            dominant_acceptor=[DominantAcceptor.OXYGEN] * n_layers,
        )
