"""Sulfur state representation for soil profile layers."""

from __future__ import annotations


from agrogame.soil.models import SoilProfile
from .constants import (
    BULK_DENSITY_G_CM3_TO_KG_M3,
    SOIL_AREA_M2_PER_HA,
    ORGANIC_MATTER_S_FRACTION,
)


class SoilSulfurState:
    """Holds sulfur pools per layer in kg/ha.

    Pools tracked per layer:
    - organic_s: Organic sulfur bound in soil organic matter (kg/ha)
    - available_s: Plant-available sulfate S in solution/exchangeable (kg/ha)
    - adsorbed_s: Reversibly adsorbed sulfate S on Fe/Al oxides (kg/ha)
    """

    def __init__(self, profile: SoilProfile):
        """Initialize sulfur pools from profile initial conditions.

        Args:
            profile: Soil profile providing initial nutrient metadata.
        """
        # Initialize available SO4-S directly from per-layer initial values
        self.available_s: list[float] = [
            layer.initial_s_kg_ha for layer in profile.layers
        ]
        # Start with no adsorbed S; accumulates reversibly via adsorption
        self.adsorbed_s: list[float] = [0.0 for _ in profile.layers]

        # Initialize organic S per layer based on soil organic matter (OM)
        self.organic_s: list[float] = []
        for layer in profile.layers:
            depth_m = layer.depth_cm / 100.0
            bulk_density_kg_m3 = layer.bulk_density_g_cm3 * BULK_DENSITY_G_CM3_TO_KG_M3
            soil_mass_kg_per_ha = bulk_density_kg_m3 * depth_m * SOIL_AREA_M2_PER_HA
            om_fraction = max(0.0, layer.organic_matter_pct) / 100.0
            om_mass_kg_per_ha = soil_mass_kg_per_ha * om_fraction
            organic_s_kg_per_ha = om_mass_kg_per_ha * ORGANIC_MATTER_S_FRACTION
            self.organic_s.append(organic_s_kg_per_ha)

    def total_sulfur_kg_ha(self) -> float:
        """Return total sulfur across pools (kg/ha)."""
        return sum(self.organic_s) + sum(self.available_s) + sum(self.adsorbed_s)
