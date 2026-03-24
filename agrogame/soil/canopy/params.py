from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanopyParams:
    extinction_coefficient_k: float  # unitless Beer-Lambert k
    radiation_use_efficiency_g_per_mj: float  # g biomass per MJ intercepted PAR
    specific_leaf_area_m2_per_g: float  # SLA
    lai_max: float
    senescence_rate_per_day: float = 0.0
    # Cardinal temperatures for RUE scaling (DSSAT/APSIM style)
    temp_base_c: float = 8.0  # below this, temp_factor = 0
    temp_opt_c: float = 30.0  # at this, temp_factor = 1
    temp_max_c: float = 42.0  # above this, temp_factor = 0


def cardinal_temp_factor(tmean_c: float, base: float, opt: float, tmax: float) -> float:
    """Piecewise-linear temperature response: 0 at base/max, 1 at optimum."""
    if tmean_c <= base or tmean_c >= tmax:
        return 0.0
    if tmean_c <= opt:
        return (tmean_c - base) / (opt - base)
    return (tmax - tmean_c) / (tmax - opt)
