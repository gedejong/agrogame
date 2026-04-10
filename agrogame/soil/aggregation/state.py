"""Mutable soil aggregation state per layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class SoilAggregationState:
    """Per-layer aggregate size distribution (fractions by mass).

    Three classes following Six et al. (2004):
    - micro: <0.02 mm (clay-organic complexes)
    - meso: 0.02-0.25 mm (silt-size aggregates)
    - macro: >0.25 mm (root/fungal-bound aggregates)

    Fractions sum to 1.0 per layer.
    """

    micro: list[float] = field(default_factory=list)
    meso: list[float] = field(default_factory=list)
    macro: list[float] = field(default_factory=list)

    @staticmethod
    def from_layers(n_layers: int) -> SoilAggregationState:
        """Initialize with typical tilled agricultural soil.

        Start: 40% micro, 35% meso, 25% macro — moderate structure.
        Ref: Six et al. 2004, Table 1.
        """
        return SoilAggregationState(
            micro=[0.40] * n_layers,
            meso=[0.35] * n_layers,
            macro=[0.25] * n_layers,
        )

    def mwd(self, layer: int) -> float:
        """Mean weight diameter (mm) — aggregate stability indicator.

        MWD = sum(fraction_i × midpoint_i) for each size class.
        Ref: Kemper & Rosenau 1986, Methods of Soil Analysis.
        """
        # Midpoints: micro=0.01mm, meso=0.135mm, macro=2.0mm
        if layer >= len(self.micro):
            return 0.0
        return (
            self.micro[layer] * 0.01
            + self.meso[layer] * 0.135
            + self.macro[layer] * 2.0
        )

    def normalize(self, layer: int) -> None:
        """Ensure fractions sum to 1.0."""
        if layer >= len(self.micro):
            return
        total = self.micro[layer] + self.meso[layer] + self.macro[layer]
        if total > 0.0:
            self.micro[layer] /= total
            self.meso[layer] /= total
            self.macro[layer] /= total

    def to_dict(self) -> Dict[str, Any]:
        return {
            "micro": list(self.micro),
            "meso": list(self.meso),
            "macro": list(self.macro),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SoilAggregationState:
        return cls(
            micro=list(data.get("micro", [])),
            meso=list(data.get("meso", [])),
            macro=list(data.get("macro", [])),
        )
