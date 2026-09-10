"""Sulfate sorption relations shared by the sulfur state and cycle.

Sulfate is held on Fe/Al-oxide and clay-edge sites by a fast, reversible
exchange that strengthens with acidity and with oxide/clay surface area
(Chao et al. 1962; Curtin & Syers 1990). The functions here express that
dependence once, so initial pool sizing and daily exchange use the same
kinetic partition. Only dissolved sulfate is transported by drainage.
"""

from __future__ import annotations

from .params import SulfurRateParams


def acidity_index(ph: float) -> float:
    """Acidity ramp shared by every sorption term: 0 at pH >= 7, 1 at pH <= 4."""
    return max(0.0, min(1.0, (7.0 - ph) / 3.0))


def clay_multiplier(clay_pct: float | None, params: SulfurRateParams) -> float:
    """Reference-normalised linear clay response, clamped to the parameter bounds.

    An unknown clay content (``None``) keeps texture modulation neutral (1.0).
    """
    reference = params.adsorption_clay_reference_pct
    if clay_pct is None or reference <= 0.0:
        return 1.0
    mult = 1.0 + params.adsorption_clay_sensitivity * (clay_pct - reference) / reference
    return max(
        params.adsorption_clay_min_mult, min(params.adsorption_clay_max_mult, mult)
    )


def adsorption_weekly_fraction(
    ph: float, clay_pct: float | None, params: SulfurRateParams
) -> float:
    """Weekly fraction of solution SO4 that adsorbs at a given pH and clay content."""
    weekly = params.adsorption_weekly_min + (
        params.adsorption_weekly_max - params.adsorption_weekly_min
    ) * acidity_index(ph)
    return weekly * clay_multiplier(clay_pct, params)


def equilibrium_adsorbed_kg_ha(
    available_kg_ha: float,
    ph: float,
    clay_pct: float | None,
    params: SulfurRateParams,
) -> float:
    """Adsorbed SO4 in kinetic balance with a given solution pool (kg S/ha).

    Net exchange vanishes when ``available x adsorb_weekly`` equals
    ``adsorbed x desorption_weekly``; the ratio of the two rate constants is
    the fast-exchange partition of a two-site sorption model (Selim 1992).
    """
    if available_kg_ha <= 0.0 or params.desorption_weekly <= 0.0:
        return 0.0
    return (
        available_kg_ha
        * adsorption_weekly_fraction(ph, clay_pct, params)
        / params.desorption_weekly
    )
