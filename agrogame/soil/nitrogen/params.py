"""Immutable nitrogen process-rate parameters.

Base daily rate constants for the soil-nitrogen transformations, previously
inline magic scalars in :mod:`agrogame.soil.nitrogen.cycle`. Collecting them in
a frozen dataclass makes them calibratable and lets rates with strong soil
dependence be modulated by texture without editing the process code.

Defaults reproduce the historical inline values exactly, so a
``NitrogenCycle`` built with ``NitrogenRateParams()`` behaves identically to
the pre-parameterization implementation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NitrogenRateParams:
    """Base daily rate constants for nitrogen transformations.

    All base rates are per-day first-order fractions applied to the relevant
    pool, then modulated in-code by temperature (Q10), moisture, aeration, pH
    and microbial-activity factors.

    Soil-texture dependence (AC3) is expressed for denitrification only, where
    the literature link to clay is strongest: finer-textured soils hold more
    water-filled pore space and anaerobic microsites, raising denitrification
    several-fold (Barton et al. 1999, Aust. J. Soil Res.; Groffman & Tiedje
    1989, SSSAJ). The clay response is reference-normalized so a soil at
    ``denit_clay_reference_pct`` clay is unchanged (multiplier 1.0); it is also
    neutral when a layer exposes no clay content.

    Attributes:
        mineralization_base_rate: Organic-N -> NH4+ first-order fraction per
            day (Stanford & Smith 1972, SSSAJ; typical ~0.5-1% of the active
            organic-N pool per day at 20 degC).
        nitrification_base_rate: NH4+ -> NO3- first-order fraction per day
            under favourable conditions (APSIM SoilN; ~10-20%/day at optimum).
        nitrification_max_rate: Upper cap on the realized daily nitrification
            fraction after all environmental factors.
        denitrification_base_rate: NO3- loss first-order fraction per day
            under fully anaerobic conditions (WOFOST/APSIM order of
            magnitude; a few %/day).
        volatilization_base_rate: Surface NH3 volatilization first-order
            fraction per day of surface NH4+ (Sommer et al. 2004, Soil Use
            Manage.; ~5%/day baseline).
        volatilization_max_rate: Upper cap on realized daily volatilization
            fraction after temperature scaling (~10%/day).
        denit_clay_reference_pct: Clay % at which the denitrification clay
            multiplier equals 1.0 (loam reference, matching TEXTURE_TO_CLAY).
        denit_clay_sensitivity: Slope of the linear clay response; the
            multiplier is ``1 + sensitivity * (clay_pct - reference) /
            reference``.
        denit_clay_min_mult: Lower clamp on the denitrification clay
            multiplier (coarse, well-aerated soils).
        denit_clay_max_mult: Upper clamp on the denitrification clay
            multiplier (heavy clay soils).
        enable_self_mineralization: When True (default), the cycle mineralises
            its own ``SoilNitrogenState.organic_n`` pool via
            ``mineralization_base_rate`` — the original AGRO-17 behaviour, kept
            so a standalone ``NitrogenCycle`` (and its unit tests) still
            produce mineral N without a SOM module. When False, the cycle does
            no self-mineralisation and treats the SOM module (3-pool RothC;
            Coleman & Jenkinson 1996) as the *single* authoritative
            N-mineralisation source, injected via ``SOMDecomposed`` events.
            The orchestrated full sim runs with this False (#351): previously
            both this pool *and* the SOM pool mineralised the same organic
            matter into NH4 every day, roughly 5× realistic net mineralisation
            (~1-3 kg N/ha/day; Stanford & Smith 1972, SSSAJ). That
            double-counting pinned root-zone mineral N implausibly high
            (~340-500 kg/ha), so uptake always met demand and neither N stress
            nor fertiliser carried consequence.
    """

    mineralization_base_rate: float = 0.001
    nitrification_base_rate: float = 0.15
    nitrification_max_rate: float = 0.20
    denitrification_base_rate: float = 0.02
    volatilization_base_rate: float = 0.05
    volatilization_max_rate: float = 0.10

    # Denitrification texture dependence (AC3)
    denit_clay_reference_pct: float = 22.0
    denit_clay_sensitivity: float = 0.5
    denit_clay_min_mult: float = 0.5
    denit_clay_max_mult: float = 2.0

    # SOM-authoritative mineralisation (#351): see class docstring.
    enable_self_mineralization: bool = True
