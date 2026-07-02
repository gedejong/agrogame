"""Immutable pore network parameters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PoreNetworkParams:
    """Pedotransfer coefficients for pore size distribution.

    Derives macropore, mesopore, micropore volume fractions from
    texture (sand, silt, clay %), organic matter, and aggregation MWD.
    Cryptopore fraction is computed as residual.

    Pore class thresholds (Greenland 1977; Luxmoore 1981):
    - Macropores:  >50 um  — rapid gravitational flow, air-filled at FC
    - Mesopores:   10-50 um — plant-available water storage
    - Micropores:  0.2-10 um — water retention, restricted biology
    - Cryptopores: <0.2 um  — excludes enzymes, protects SOM

    PTF approach: retention-curve partition.
    - Macroporosity ~ saturation - field_capacity (drains by gravity)
    - Mesoporosity  ~ field_capacity - wilting_point (plant-available)
    - Microporosity ~ wilting_point - residual_water
    - Cryptoporosity = total_porosity - (macro + meso + micro)

    Aggregation adjusts macroporosity: well-aggregated soil creates
    inter-aggregate macropores. Ref: Dexter 2004, Geoderma.

    Macroporosity calibration (#340):
        The gravitational-drainage pool (saturation - field_capacity)
        empties between saturation and field capacity (~ -6 to -33 kPa,
        i.e. pores >~9 um at FC). That pool is NOT all true macroporosity:
        it also contains coarse *transmission mesopores* (10-50 um) that
        are air-filled at FC but are not >50 um macropores. Equating the
        whole drainable pool with macroporosity overestimates it (loam
        read ~0.20 vs the literature air-capacity/macroporosity band of
        ~5-15%). We therefore split the drainable pool into true
        macroporosity (>50 um) and coarse mesoporosity, with the
        macropore share rising with sand content — coarse soils are
        macropore-dominated, medium/fine soils hold proportionally more
        transmission mesopores.
        Refs: Luxmoore 1981, SSSAJ (pore-size classes); Cameron & Buchan
        2006, Encyclopedia of Soil Science (air capacity); Reynolds et
        al. 2002 Geoderma & 2009 Geoderma (air-capacity/macroporosity
        indicators, optimum ~0.05-0.15).

    Attributes:
        mwd_baseline: MWD value at which aggregation has no effect on
            macroporosity (typical tilled soil). Ref: Six et al. 2004.
        mwd_macro_coeff: Macroporosity bonus per unit MWD above baseline.
            Ref: Bronick & Lal 2005 — 2-5% macroporosity increase per
            mm MWD improvement.
        macro_split_base: Fraction of the drainable pool (sat - FC) that
            is true macroporosity (>50 um) at 0% sand. Ref: #340 above.
        macro_split_sand_slope: Increase in that macropore share per 1%
            sand. Calibrated so sand -> ~1.0 (drainable pool is nearly all
            macropores), loam -> ~0.5, clay -> ~0.3.
        residual_water_intercept: Intercept for residual water PTF.
            Linear fit to Rawls et al. 1982 Table 2 theta_r vs clay%:
            theta_r = 0.0096 + 0.00163 * clay%.
        residual_water_slope: Slope for residual water PTF (per clay%).
        min_macro_frac: Minimum macropore fraction (severely degraded).
        max_macro_frac: Maximum macropore fraction (coarse sand).
    """

    mwd_baseline: float = 0.5
    mwd_macro_coeff: float = 0.025
    macro_split_base: float = 0.08
    macro_split_sand_slope: float = 0.01
    residual_water_intercept: float = 0.0096
    residual_water_slope: float = 0.00163
    min_macro_frac: float = 0.01
    max_macro_frac: float = 0.30
