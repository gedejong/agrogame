from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CanopyState:
    lai: float
    biomass_g_m2: float
    stem_biomass_g_m2: float = 0.0
    grain_biomass_g_m2: float = 0.0
    last_water_stress: float = 1.0  # 1=no stress, 0=severe (supply/demand)


@dataclass
class CanopyFluxes:
    intercepted_par_mj_m2: float
    biomass_increment_g_m2: float
