"""Shared types for sulfur module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SulfurFluxes:
    """Diagnostic fluxes for a daily sulfur step (kg/ha).

    ``adsorbed_kg_ha`` is the *net* SO4 movement into the adsorbed pool
    (negative under net desorption). ``leached_kg_ha`` is reported as 0.0
    from ``daily_step``: sulfate leaching is event-driven (``WaterDrained``)
    and surfaces via :class:`NutrientLeached`, mirroring nitrate.
    """

    mineralized_kg_ha: float
    adsorbed_kg_ha: float
    plant_uptake_kg_ha: float
    leached_kg_ha: float
