"""Nitrogen state representation for soil profile layers."""

from __future__ import annotations


from agrogame.soil.models import SoilProfile
from agrogame.soil.nitrogen.constants import (
    BULK_DENSITY_G_CM3_TO_KG_M3,
    SOIL_AREA_M2_PER_HA,
    ORGANIC_MATTER_N_FRACTION,
)


class SoilNitrogenState:
    """Holds nitrogen pools per layer in kg/ha.

    Pools tracked per layer:
    - organic_n: Organic nitrogen (kg/ha)
    - nh4: Ammonium (kg/ha)
    - no3: Nitrate (kg/ha)
    """

    def __init__(self, profile: SoilProfile):
        """Initialize nitrogen pools from profile initial conditions.

        Args:
            profile: Soil profile providing initial nutrient metadata.
        """
        # Initialize inorganic pools directly from per-layer initial values
        self.nh4: list[float] = [layer.initial_nh4_kg_ha for layer in profile.layers]
        self.no3: list[float] = [layer.initial_no3_kg_ha for layer in profile.layers]

        # Initialize organic N per layer based on soil organic matter (OM)
        # Assumption: 5% of OM mass is nitrogen (simplified agronomic rule of thumb)
        self.organic_n: list[float] = []
        for layer in profile.layers:
            depth_m = layer.depth_cm / 100.0
            bulk_density_kg_m3 = layer.bulk_density_g_cm3 * BULK_DENSITY_G_CM3_TO_KG_M3
            soil_mass_kg_per_ha = bulk_density_kg_m3 * depth_m * SOIL_AREA_M2_PER_HA
            om_fraction = max(0.0, layer.organic_matter_pct) / 100.0
            om_mass_kg_per_ha = soil_mass_kg_per_ha * om_fraction
            organic_n_kg_per_ha = om_mass_kg_per_ha * ORGANIC_MATTER_N_FRACTION
            self.organic_n.append(organic_n_kg_per_ha)

    def total_nitrogen_kg_ha(self) -> float:
        """Return total nitrogen across pools (kg/ha)."""
        return sum(self.organic_n) + sum(self.nh4) + sum(self.no3)
