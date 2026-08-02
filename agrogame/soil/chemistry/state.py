"""Mutable soil chemistry state per soil layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChemistryState:
    """Per-layer soil pH.

    Attributes:
        ph: pH value per soil layer.
    """

    ph: list[float] = field(default_factory=list)

    @classmethod
    def from_layers(cls, n_layers: int, base_ph: float = 6.8) -> ChemistryState:
        """Initialise all layers at ``base_ph``."""
        return cls(ph=[float(base_ph)] * n_layers)
