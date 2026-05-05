"""Back-compat shim — canopy params live at agrogame.params.canopy (#300).

The ``cardinal_temp_factor`` helper stays here because it's a runtime
utility rather than a parameter type, and several soil-side modules call
it directly.
"""

from __future__ import annotations

from agrogame.params.canopy import CanopyParams

__all__ = ["CanopyParams", "cardinal_temp_factor"]


def cardinal_temp_factor(tmean_c: float, base: float, opt: float, tmax: float) -> float:
    """Curvilinear temperature response (DSSAT/APSIM style).

    Below optimum: concave (sqrt) curve — rises quickly from base,
    matching the beta-function shape used in DSSAT CERES models.
    Above optimum: linear decline — crops are more sensitive to
    supra-optimal heat.

    Returns 0 at base and max, 1 at optimum.
    """
    if tmean_c <= base or tmean_c >= tmax:
        return 0.0
    if tmean_c <= opt:
        x = (tmean_c - base) / (opt - base)
        return float(x**0.5)
    return (tmax - tmean_c) / (tmax - opt)
