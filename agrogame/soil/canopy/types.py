from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CanopyState:
    lai: float
    biomass_g_m2: float


@dataclass
class CanopyFluxes:
    intercepted_par_mj_m2: float
    biomass_increment_g_m2: float
