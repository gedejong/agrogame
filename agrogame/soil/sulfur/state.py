"""Sulfur state representation for soil profile layers."""

from __future__ import annotations


from agrogame.soil.models import SoilProfile
from .constants import (
    BULK_DENSITY_G_CM3_TO_KG_M3,
    DEFAULT_SOIL_PH,
    SOIL_AREA_M2_PER_HA,
    ORGANIC_MATTER_S_FRACTION,
)
from .params import SulfurRateParams
from .sorption import equilibrium_adsorbed_kg_ha


class SoilSulfurState:
    """Holds sulfur pools per layer in kg/ha.

    Pools tracked per layer:
    - organic_s: Organic sulfur bound in soil organic matter (kg/ha)
    - available_s: Plant-available sulfate S in solution/exchangeable (kg/ha)
    - adsorbed_s: Reversibly adsorbed sulfate S on Fe/Al oxides (kg/ha)
    """

    def __init__(
        self, profile: SoilProfile, params: SulfurRateParams | None = None
    ) -> None:
        """Initialize sulfur pools from profile initial conditions.

        Args:
            profile: Soil profile providing initial nutrient metadata.
            params: Sorption rate constants that size the initial adsorbed
                pool; the defaults match those of the sulfur cycle.
        """
        rates = params if params is not None else SulfurRateParams()
        # Initialize available SO4-S directly from per-layer initial values
        self.available_s: list[float] = [
            layer.initial_s_kg_ha for layer in profile.layers
        ]
        # Adsorbed SO4 starts in kinetic equilibrium with the solution pool at
        # the default pH: a soil has equilibrated its sorbed and dissolved
        # sulfate over years, whereas an empty sorbed pool would turn the first
        # weeks of a simulation into a net sink for solution SO4.
        self.adsorbed_s: list[float] = [
            equilibrium_adsorbed_kg_ha(
                layer.initial_s_kg_ha,
                DEFAULT_SOIL_PH,
                getattr(layer, "clay_pct", None),
                rates,
            )
            for layer in profile.layers
        ]

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
