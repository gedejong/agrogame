"""Nitrogen state representation for soil profile layers."""

from __future__ import annotations

from typing import List

from agrogame.soil.models import SoilProfile


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
        n_layers = len(profile.layers)
        # Simple initialization: put initial values in the top layer only
        self.organic_n: List[float] = [0.0 for _ in range(n_layers)]
        self.nh4: List[float] = [0.0 for _ in range(n_layers)]
        self.no3: List[float] = [0.0 for _ in range(n_layers)]
        if n_layers > 0:
            self.no3[0] = profile.layers[0].initial_no3_kg_ha
            self.nh4[0] = profile.layers[0].initial_nh4_kg_ha

    def total_nitrogen_kg_ha(self) -> float:
        """Return total nitrogen across pools (kg/ha)."""
        return sum(self.organic_n) + sum(self.nh4) + sum(self.no3)
