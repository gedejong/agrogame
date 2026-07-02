"""Immutable phosphorus process-rate parameters.

Base rate constants for the soil-phosphorus transformations, previously inline
scalars in :mod:`agrogame.soil.phosphorus.cycle` (and the module-level floats
in ``constants.py``). Collecting them in a frozen dataclass makes them
calibratable and lets fixation carry an explicit, literature-anchored soil
dependence.

Defaults reproduce the historical behaviour exactly, so a ``PhosphorusCycle``
built with ``PhosphorusRateParams()`` matches the pre-parameterization
implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PhosphorusRateParams:
    """Base rate constants for phosphorus transformations.

    Soil-texture dependence (AC3) is applied to fixation, where the link to
    clay and Fe/Al-oxide surface area is strongest: sorption capacity rises
    steeply with clay content, giving the 2-5x soil-type spread in P fixation
    reported by Barrow (1983, J. Soil Sci.) and Sanyal & De Datta (1991, Adv.
    Soil Sci.). The clay response is reference-normalized so a soil at
    ``fixation_clay_reference_pct`` clay is unchanged (multiplier 1.0); it is
    also neutral when a layer exposes no clay content.

    Attributes:
        mineralization_monthly_min: Lower bound of organic-P -> available-P
            mineralization fraction per month at the reference temperature
            (~0.5%/month; Oehl et al. 2001, SSSAJ order of magnitude).
        mineralization_monthly_max: Upper bound of the monthly mineralization
            fraction (~2%/month). The realized daily base rate is the mid-point
            of the two bounds divided by 30.
        fixation_weekly_min: Weekly fixation fraction of available P at/above
            neutral pH (equilibrium regime; Barrow 1983, Sanyal & De Datta
            1991). Reduced from the older 1-5%/week to reflect that native P is
            largely in adsorption equilibrium (see AGRO-97).
        fixation_weekly_max: Weekly fixation fraction under strongly acidic
            conditions, before texture modulation.
        fixation_clay_reference_pct: Clay % at which the fixation clay
            multiplier equals 1.0 (loam reference, matching TEXTURE_TO_CLAY).
        fixation_clay_sensitivity: Slope of the linear clay response; the
            multiplier is ``1 + sensitivity * (clay_pct - reference) /
            reference``.
        fixation_clay_min_mult: Lower clamp on the fixation clay multiplier
            (coarse, low-sorption soils).
        fixation_clay_max_mult: Upper clamp on the fixation clay multiplier
            (heavy clay / oxide-rich soils).
    """

    mineralization_monthly_min: float = 0.005
    mineralization_monthly_max: float = 0.02
    fixation_weekly_min: float = 0.002
    fixation_weekly_max: float = 0.01

    # Fixation texture dependence (AC3)
    fixation_clay_reference_pct: float = 22.0
    fixation_clay_sensitivity: float = 1.0
    fixation_clay_min_mult: float = 0.3
    fixation_clay_max_mult: float = 3.0
