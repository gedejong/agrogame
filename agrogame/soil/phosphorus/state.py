"""Phosphorus state representation for soil profile layers."""

from __future__ import annotations

from typing import List

from agrogame.soil.models import SoilProfile
from .constants import (
    BULK_DENSITY_G_CM3_TO_KG_M3,
    SOIL_AREA_M2_PER_HA,
    ORGANIC_MATTER_P_FRACTION,
)


class SoilPhosphorusState:
    """Holds phosphorus pools per layer in kg/ha.

    Pools tracked per layer:
    - organic_p: Organic phosphorus (kg/ha)
    - available_p: Plant-available inorganic P (kg/ha)
    - fixed_p: Unavailable fixed P (kg/ha)
    """

    def __init__(self, profile: SoilProfile):
        """Initialize phosphorus pools from profile initial conditions.

        Args:
            profile: Soil profile providing initial nutrient metadata.
        """
        # Initialize available P directly from per-layer initial values
        self.available_p: List[float] = [
            layer.initial_p_kg_ha for layer in profile.layers
        ]
        # Start with no fixed P; will accumulate via fixation
        self.fixed_p: List[float] = [0.0 for _ in profile.layers]

        # Initialize organic P per layer based on soil organic matter (OM)
        # Rule of thumb: 0.2% of OM mass as P, adjustable via constant
        self.organic_p: List[float] = []
        for layer in profile.layers:
            depth_m = layer.depth_cm / 100.0
            bulk_density_kg_m3 = layer.bulk_density_g_cm3 * BULK_DENSITY_G_CM3_TO_KG_M3
            soil_mass_kg_per_ha = bulk_density_kg_m3 * depth_m * SOIL_AREA_M2_PER_HA
            om_fraction = max(0.0, layer.organic_matter_pct) / 100.0
            om_mass_kg_per_ha = soil_mass_kg_per_ha * om_fraction
            organic_p_kg_per_ha = om_mass_kg_per_ha * ORGANIC_MATTER_P_FRACTION
            self.organic_p.append(organic_p_kg_per_ha)

    def total_phosphorus_kg_ha(self) -> float:
        """Return total phosphorus across pools (kg/ha)."""
        return sum(self.organic_p) + sum(self.available_p) + sum(self.fixed_p)
