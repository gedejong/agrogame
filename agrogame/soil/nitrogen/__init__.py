"""Nitrogen cycling module scaffolding.

This package provides a minimal structure for soil nitrogen processes and
integration with the water model via domain events. It is intentionally
lightweight to allow iterative development.
"""

from __future__ import annotations

from .events import NutrientLeached, NitrificationOccurred
from .state import SoilNitrogenState
from .types import NitrogenFluxes
from .cycle import NitrogenCycle

__all__ = [
    "NutrientLeached",
    "NitrificationOccurred",
    "SoilNitrogenState",
    "NitrogenFluxes",
    "NitrogenCycle",
]
