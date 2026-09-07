"""Sulfate sorption relations shared by the sulfur state and cycle.

Sulfate is held on Fe/Al-oxide and clay-edge sites by a fast, reversible
exchange that strengthens with acidity and with oxide/clay surface area
(Chao et al. 1962; Curtin & Syers 1990). The functions here express that
dependence once, so the initial sorbed pool, the daily adsorption step and
the leaching retardation stay mutually consistent.
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


def distribution_coefficient_l_per_kg(
    ph: float, clay_pct: float | None, params: SulfurRateParams
) -> float:
    """Linear sorption coefficient Kd (L/kg) for sulfate in a layer.

    The reference Kd is scaled by the same clay multiplier as the adsorption
    rate and doubles between neutral and strongly acid soil, the direction of
    the pH and oxide-surface dependence of sulfate retention (Chao et al.
    1962; Curtin & Syers 1990).
    """
    return (
        params.kd_reference_l_per_kg
        * clay_multiplier(clay_pct, params)
        * (1.0 + acidity_index(ph))
    )


def retardation_factor(
    bulk_density_g_cm3: float, theta: float, kd_l_per_kg: float
) -> float:
    """Retardation factor ``R = 1 + rho_b * Kd / theta`` of linear sorption.

    The solution phase carries ``1/R`` of a sorbing solute's pool with the
    drainage front (Jury & Horton 2004, solute transport). Bulk density in
    g/cm3 equals kg/L, so ``rho_b * Kd`` is dimensionless and ``theta`` is the
    volumetric water content. A dry or non-sorbing layer returns 1.
    """
    if theta <= 0.0 or kd_l_per_kg <= 0.0 or bulk_density_g_cm3 <= 0.0:
        return 1.0
    return 1.0 + bulk_density_g_cm3 * kd_l_per_kg / theta
