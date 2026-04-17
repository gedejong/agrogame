"""Mutable pore network state per soil layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PoreNetworkState:
    """Per-layer pore size distribution (volume fractions).

    Four classes following Greenland 1977 / Luxmoore 1981:
    - macro: >50 um  (rapid flow, air-filled at field capacity)
    - meso:  10-50 um (plant-available water storage)
    - micro: 0.2-10 um (water retention, restricted biology)
    - crypto: <0.2 um (excludes enzymes, protects SOM)

    Fractions sum to total porosity (saturation) per layer.
    Connectivity is a structural index in [0, 1].
    """

    macro: list[float] = field(default_factory=list)
    meso: list[float] = field(default_factory=list)
    micro: list[float] = field(default_factory=list)
    crypto: list[float] = field(default_factory=list)
    connectivity: list[float] = field(default_factory=list)

    @classmethod
    def empty(cls, n_layers: int) -> PoreNetworkState:
        """Create zeroed state for n_layers (populated by module.compute)."""
        return cls(
            macro=[0.0] * n_layers,
            meso=[0.0] * n_layers,
            micro=[0.0] * n_layers,
            crypto=[0.0] * n_layers,
            connectivity=[0.0] * n_layers,
        )

    def total_porosity(self, layer: int) -> float:
        """Sum of all pore fractions for a layer."""
        return (
            self.macro[layer]
            + self.meso[layer]
            + self.micro[layer]
            + self.crypto[layer]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro": list(self.macro),
            "meso": list(self.meso),
            "micro": list(self.micro),
            "crypto": list(self.crypto),
            "connectivity": list(self.connectivity),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PoreNetworkState:
        return cls(
            macro=list(data.get("macro", [])),
            meso=list(data.get("meso", [])),
            micro=list(data.get("micro", [])),
            crypto=list(data.get("crypto", [])),
            connectivity=list(data.get("connectivity", [])),
        )
