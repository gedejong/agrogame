"""Mutable biopore state per soil layer (#215)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, List


@dataclass
class BioporeState:
    """Per-layer biopore inventory.

    Tracks count density, mean radius, and volume fraction. Volume
    fraction is derived from density and radius — biopores are modelled
    as cylinders spanning the layer thickness, so the volume fraction
    is dimensionally ``density_per_m² × π × r²_m²`` regardless of
    layer depth.

    Earthworm contributions are stubbed via ``add_earthworm_biopores``
    pending #76 (soil fauna).
    """

    density_per_m2: List[float] = field(default_factory=list)
    mean_radius_mm: List[float] = field(default_factory=list)
    volume_fraction: List[float] = field(default_factory=list)

    @classmethod
    def from_layers(cls, n_layers: int, mean_radius_mm: float = 2.0) -> BioporeState:
        return cls(
            density_per_m2=[0.0] * n_layers,
            mean_radius_mm=[mean_radius_mm] * n_layers,
            volume_fraction=[0.0] * n_layers,
        )

    @staticmethod
    def density_to_volume_fraction(density_per_m2: float, radius_mm: float) -> float:
        """Cylindrical-pore volume fraction (m³/m³).

        Each biopore is a cylinder with radius ``r`` spanning the
        layer thickness ``d``: volume per pore is π·r²·d. Across a
        unit horizontal area, total biopore volume is
        ``density × π·r²·d``, and the layer's bulk volume is
        ``1·d``, so the fraction is ``density × π·r²`` (depth cancels).
        """
        radius_m = radius_mm * 1e-3
        return float(density_per_m2 * math.pi * radius_m * radius_m)

    def recompute_volume_fraction(self) -> None:
        """Refresh ``volume_fraction`` from current density × radius."""
        for i in range(len(self.density_per_m2)):
            r = self.mean_radius_mm[i] if i < len(self.mean_radius_mm) else 2.0
            self.volume_fraction[i] = self.density_to_volume_fraction(
                self.density_per_m2[i], r
            )

    def add_earthworm_biopores(
        self, layer: int, count: float, mean_radius_mm: float
    ) -> None:
        """Stub for earthworm-burrow contributions — full implementation
        deferred to #76 (soil fauna). Adds count at the given radius
        without going through any rate / decay path; caller is
        responsible for keeping totals physically meaningful.
        """
        if layer < 0 or layer >= len(self.density_per_m2):
            return
        prev_density = self.density_per_m2[layer]
        new_density = prev_density + count
        if new_density <= 0.0:
            self.density_per_m2[layer] = 0.0
            self.volume_fraction[layer] = 0.0
            return
        # Density-weighted mean radius.
        prev_radius = self.mean_radius_mm[layer]
        weighted_r = (prev_density * prev_radius + count * mean_radius_mm) / new_density
        self.density_per_m2[layer] = new_density
        self.mean_radius_mm[layer] = weighted_r
        self.volume_fraction[layer] = self.density_to_volume_fraction(
            new_density, weighted_r
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "density_per_m2": list(self.density_per_m2),
            "mean_radius_mm": list(self.mean_radius_mm),
            "volume_fraction": list(self.volume_fraction),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BioporeState:
        return cls(
            density_per_m2=list(data.get("density_per_m2", [])),
            mean_radius_mm=list(data.get("mean_radius_mm", [])),
            volume_fraction=list(data.get("volume_fraction", [])),
        )
