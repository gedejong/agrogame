from __future__ import annotations

import math


def saturation_vapor_pressure_kpa(temp_c: float) -> float:
    return 0.6108 * math.exp(17.27 * temp_c / (temp_c + 237.3))


def vpd_kpa(temp_mean_c: float, relative_humidity_pct: float) -> float:
    es = saturation_vapor_pressure_kpa(temp_mean_c)
    ea = es * max(0.0, min(1.0, relative_humidity_pct / 100.0))
    return max(0.0, es - ea)


def net_radiation_from_shortwave(
    rs_mj_m2: float,
    albedo: float,
    lw_net_mj_m2: float = 0.0,
) -> float:
    """Approximate net radiation from shortwave and albedo plus optional LW net."""
    return max(0.0, rs_mj_m2 * (1.0 - max(0.0, min(1.0, albedo))) + lw_net_mj_m2)
