from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class StressFactors:
    """Shared stress factors for modules that react to water/N stress.

    Values are in 0..1, where lower means more stress.
    """

    water: float = 1.0
    nitrogen: float = 1.0
    phosphorus: float = 1.0
    sulfur: float = 1.0


def compute_water_stress(
    actual_transpiration_mm: float, potential_transpiration_mm: float
) -> float:
    """Return 0..1 water stress based on supply/demand of transpiration.

    - If demand is zero, returns 1.0 (no stress by definition).
    - Otherwise, returns clamp(actual / demand, 0..1).
    """
    demand = max(0.0, potential_transpiration_mm)
    if demand <= 0.0:
        return 1.0
    supply = max(0.0, actual_transpiration_mm)
    return max(0.0, min(1.0, supply / demand))


class StressCalculator:
    """Utilities to compute and combine plant stress factors.

    This class centralizes stress computations so different modules can use a
    consistent policy. Factors are always clamped to [0, 1], where 1 means no
    stress and 0 means full limitation.
    """

    def __init__(self, combine_method: Literal["liebig", "multiplicative"] = "liebig"):
        self.combine_method: Literal["liebig", "multiplicative"] = combine_method

    @staticmethod
    def water_from_supply_demand(actual_mm: float, potential_mm: float) -> float:
        """Compute water stress from supply/demand ratio (actual/potential)."""
        return compute_water_stress(actual_mm, potential_mm)

    @staticmethod
    def nutrient_from_uptake_demand(uptake_kg_ha: float, demand_kg_ha: float) -> float:
        """Proxy nutrient stress from uptake vs demand.

        If demand is zero or negative, returns 1.0 (no stress). Otherwise returns
        clamp(uptake / demand, 0..1).
        """
        demand = max(0.0, float(demand_kg_ha))
        if demand <= 0.0:
            return 1.0
        uptake = max(0.0, float(uptake_kg_ha))
        return max(0.0, min(1.0, uptake / demand))

    @staticmethod
    def nutrient_from_concentration(
        tissue_conc: float, optimal_conc: float, critical_conc: float
    ) -> float:
        """Compute nutrient stress from tissue concentration thresholds.

        Piecewise-linear response:
        - tissue >= optimal -> 1.0
        - tissue <= critical -> 0.0
        - linear between critical and optimal
        """
        opt = max(0.0, float(optimal_conc))
        crit = max(0.0, float(critical_conc))
        val = max(0.0, float(tissue_conc))
        if opt <= crit:
            # Degenerate thresholds: treat as step around opt
            return 1.0 if val >= opt else 0.0
        if val >= opt:
            return 1.0
        if val <= crit:
            return 0.0
        # Linear interpolation between [crit, opt]
        return (val - crit) / (opt - crit)

    def combine(
        self,
        water: float,
        nitrogen: float,
        phosphorus: float,
        sulfur: float = 1.0,
    ) -> float:
        """Combine stress factors according to configured method.

        - liebig: minimum of the individual factors
        - multiplicative: product of the individual factors

        ``sulfur`` defaults to 1.0 (no limitation) so existing callers that
        pass only water/N/P are unaffected.
        """
        w = max(0.0, min(1.0, float(water)))
        n = max(0.0, min(1.0, float(nitrogen)))
        p = max(0.0, min(1.0, float(phosphorus)))
        s = max(0.0, min(1.0, float(sulfur)))
        if self.combine_method == "multiplicative":
            return w * n * p * s
        # Default Liebig's law (most limiting factor)
        return min(w, n, p, s)
