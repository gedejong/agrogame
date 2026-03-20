"""Shared types for phosphorus module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhosphorusFluxes:
    """Diagnostic fluxes for a daily phosphorus step (kg/ha)."""

    mineralized_kg_ha: float
    fixed_kg_ha: float
    plant_uptake_kg_ha: float
    leached_kg_ha: float
