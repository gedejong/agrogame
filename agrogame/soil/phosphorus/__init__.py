"""Phosphorus cycling module scaffolding."""

from __future__ import annotations

from .events import PhosphorusFixationOccurred
from .state import SoilPhosphorusState
from .types import PhosphorusFluxes
from .cycle import PhosphorusCycle

__all__ = [
    "PhosphorusFixationOccurred",
    "SoilPhosphorusState",
    "PhosphorusFluxes",
    "PhosphorusCycle",
]
