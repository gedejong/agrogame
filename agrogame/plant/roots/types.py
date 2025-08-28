from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class RootState:
    current_depth_cm: float = 5.0
    biomass_g_m2: float = 0.0
    layer_fractions: List[float] | None = None


@dataclass(frozen=True)
class RootFluxes:
    depth_inc_cm: float
    biomass_delta_g_m2: float
