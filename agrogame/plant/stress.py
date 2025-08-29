from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StressFactors:
    """Shared stress factors for modules that react to water/N stress.

    Values are in 0..1, where lower means more stress.
    """

    water: float = 1.0
    nitrogen: float = 1.0


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
