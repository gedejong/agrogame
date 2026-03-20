"""Nitrogen model shared types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NitrogenFluxes:
    """Diagnostic nitrogen fluxes for a daily step (kg/ha)."""

    mineralized_kg_ha: float
    nitrified_kg_ha: float
    denitrified_kg_ha: float
    plant_uptake_kg_ha: float
    leached_kg_ha: float
