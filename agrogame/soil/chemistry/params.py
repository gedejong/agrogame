"""Immutable soil chemistry parameters.

Holds the base pH, the daily buffering rate and target, and the per-event
pH increments and clamping bounds used by :class:`SoilChemistryModule`.
Extracted from hard-coded constants in ``module.py`` (#288) so the pH
dynamics are declarative and characterised, not implied.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChemistryParams:
    """Coefficients governing per-layer soil pH dynamics.

    The values reproduce the previously hard-coded heuristics exactly; this
    is a structural extraction with no behaviour change (#288).

    Attributes:
        base_ph: Initial per-layer pH when state is built from defaults.
        default_target_ph: Buffering target used when a ``DayTick`` carries
            no explicit ``target_ph``.
        buffering_rate: Daily fraction of the gap to ``target_ph`` that pH
            relaxes towards (weak buffering tendency).
        no3_leach_ph_delta: pH drop applied on nitrate (NO3) leaching —
            nitrate loss tends to acidify slightly.
        p_fixation_ph_delta: pH drop applied when phosphorus fixation occurs
            (a small local acidification proxy).
        lime_ph_delta_per_kg_ha: pH rise per kg/ha of applied lime
            (CaCO3-equivalent neutralisation).
        acidifying_ph_delta_per_kg_ha: pH drop per kg/ha of acidifying
            fertilizer applied.
        ph_floor: Lower clamp on per-layer pH.
        ph_ceiling: Upper clamp on per-layer pH.
    """

    base_ph: float = 6.8
    default_target_ph: float = 6.8
    buffering_rate: float = 0.001
    no3_leach_ph_delta: float = 0.005
    p_fixation_ph_delta: float = 0.002
    lime_ph_delta_per_kg_ha: float = 0.001
    acidifying_ph_delta_per_kg_ha: float = 0.0005
    ph_floor: float = 4.0
    ph_ceiling: float = 9.0
