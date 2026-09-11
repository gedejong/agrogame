"""Immutable sulfur process-rate parameters.

Base rate constants for the (non-redox) soil-sulfur transformations,
collected in a frozen dataclass so they are calibratable and the adsorption
term can carry an explicit, literature-anchored soil dependence — mirroring
:class:`agrogame.soil.phosphorus.params.PhosphorusRateParams`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SulfurRateParams:
    """Base rate constants for sulfur transformations.

    Mineralization is anchored to the emergent *field* net flux: with the
    corrected organic-S pool (~2,000-2,400 kg S/ha for a 3% OM profile;
    ORGANIC_MATTER_S_FRACTION = 0.008), net organic-S mineralization must
    stay in the literature ~5-20 kg S/ha/yr band, i.e. ~0.2-0.9 %/yr net
    turnover under realistic seasonal soil temperatures. The monthly base
    bounds below (0.0006-0.0012 /month at the 25 °C reference, temperature-
    and moisture-scaled) integrate to ~12 kg S/ha/yr over a temperate season
    — the centre of that band. These are *not* a lab-incubation %/month rate;
    the previous 0.01-0.03 /month values were a ~25x too-fast lab anchor that
    compensated for a ~25x too-small pool (#386), yielding a plausible flux
    for the wrong reasons.
    Ref: Eriksen (2009) Adv. Agron. 102 (net field S mineralization
    5-20 kg/ha/yr; C/N/S turnover coupling); Scherer (2001) Eur. J. Agron.
    14:81-111 (soil-S mineralization and crop response).

    SO4 adsorption is reversible and rises with acidity and Fe/Al-oxide
    (clay) surface area, but is markedly weaker and more labile than phosphate
    fixation (Bolan et al. 1988, J. Soil Sci.; Curtin & Syers 1990, J. Soil
    Sci.; Marsh et al. 1987). The clay response is reference-normalized so a
    loam-textured layer is unchanged (multiplier 1.0).

    Attributes:
        mineralization_monthly_min: Lower bound of organic-S -> SO4
            mineralization fraction per month at the 25 °C reference
            (0.06 %/month). The realized daily base rate is the mid-point of
            the two bounds divided by 30, then temperature/moisture/microbe
            scaled. Calibrated so the season-summed net flux lands in the
            5-20 kg S/ha/yr field band on the corrected organic-S pool.
        mineralization_monthly_max: Upper bound of the monthly mineralization
            fraction (0.12 %/month at the 25 °C reference).
        adsorption_weekly_min: Weekly SO4-adsorption fraction of the available
            pool at/above neutral pH (equilibrium regime).
        adsorption_weekly_max: Weekly SO4-adsorption fraction under strongly
            acidic conditions, before texture modulation.
        desorption_weekly: Weekly fraction of the adsorbed pool released back
            to solution, giving the reversibility characteristic of sulfate
            (unlike near-irreversible P fixation).
        adsorption_clay_reference_pct: Clay % at which the adsorption clay
            multiplier equals 1.0 (loam reference, matching TEXTURE_TO_CLAY).
        adsorption_clay_sensitivity: Slope of the linear clay response.
        adsorption_clay_min_mult: Lower clamp on the clay multiplier.
        adsorption_clay_max_mult: Upper clamp on the clay multiplier.
    """

    mineralization_monthly_min: float = 0.0006
    mineralization_monthly_max: float = 0.0012

    # SO4 adsorption / desorption (weaker + reversible vs. P fixation)
    adsorption_weekly_min: float = 0.003
    adsorption_weekly_max: float = 0.015
    desorption_weekly: float = 0.01

    # Adsorption texture dependence
    adsorption_clay_reference_pct: float = 22.0
    adsorption_clay_sensitivity: float = 0.75
    adsorption_clay_min_mult: float = 0.3
    adsorption_clay_max_mult: float = 3.0
