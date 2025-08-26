from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanopyParams:
    extinction_coefficient_k: float  # unitless Beer-Lambert k
    radiation_use_efficiency_g_per_mj: float  # g biomass per MJ intercepted PAR
    specific_leaf_area_m2_per_g: float  # SLA
    lai_max: float
    senescence_rate_per_day: float = 0.0
