"""Mutable micronutrient state per soil layer."""

from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.soil.micronutrients.constants import (
    DEFAULT_AVAIL_FRACTION_FE,
    DEFAULT_AVAIL_FRACTION_MN,
    DEFAULT_AVAIL_FRACTION_ZN,
    DEFAULT_TOTAL_FE_PPM,
    DEFAULT_TOTAL_MN_PPM,
    DEFAULT_TOTAL_ZN_PPM,
)


@dataclass
class MicronutrientState:
    """Per-layer available and total pools for Fe, Zn, Mn (ppm).

    Available = DTPA-extractable fraction (plant-accessible).
    Total = includes unavailable/sorbed forms.
    """

    fe_available: list[float] = field(default_factory=list)
    fe_total: list[float] = field(default_factory=list)
    zn_available: list[float] = field(default_factory=list)
    zn_total: list[float] = field(default_factory=list)
    mn_available: list[float] = field(default_factory=list)
    mn_total: list[float] = field(default_factory=list)

    @staticmethod
    def from_layers(n_layers: int) -> MicronutrientState:
        """Initialize with default agricultural soil values."""
        return MicronutrientState(
            fe_available=[DEFAULT_TOTAL_FE_PPM * DEFAULT_AVAIL_FRACTION_FE] * n_layers,
            fe_total=[DEFAULT_TOTAL_FE_PPM] * n_layers,
            zn_available=[DEFAULT_TOTAL_ZN_PPM * DEFAULT_AVAIL_FRACTION_ZN] * n_layers,
            zn_total=[DEFAULT_TOTAL_ZN_PPM] * n_layers,
            mn_available=[DEFAULT_TOTAL_MN_PPM * DEFAULT_AVAIL_FRACTION_MN] * n_layers,
            mn_total=[DEFAULT_TOTAL_MN_PPM] * n_layers,
        )

    @staticmethod
    def from_profile(profile: object) -> MicronutrientState:
        """Initialize from a SoilProfile with per-layer DTPA values.

        Uses initial_fe_ppm/zn_ppm/mn_ppm from each SoilLayer if available.
        Total pools estimated as available / typical DTPA fraction.
        Ref: Sims & Johnson 1991, Micronutrient Soil Tests.
        """
        layers = getattr(profile, "layers", [])
        n = len(layers)
        if n == 0:
            return MicronutrientState.from_layers(0)
        fe_a, fe_t = [], []
        zn_a, zn_t = [], []
        mn_a, mn_t = [], []
        for ly in layers:
            fe = getattr(
                ly, "initial_fe_ppm", DEFAULT_TOTAL_FE_PPM * DEFAULT_AVAIL_FRACTION_FE
            )
            zn = getattr(
                ly, "initial_zn_ppm", DEFAULT_TOTAL_ZN_PPM * DEFAULT_AVAIL_FRACTION_ZN
            )
            mn = getattr(
                ly, "initial_mn_ppm", DEFAULT_TOTAL_MN_PPM * DEFAULT_AVAIL_FRACTION_MN
            )
            fe_a.append(fe)
            fe_t.append(fe / max(DEFAULT_AVAIL_FRACTION_FE, 1e-9))
            zn_a.append(zn)
            zn_t.append(zn / max(DEFAULT_AVAIL_FRACTION_ZN, 1e-9))
            mn_a.append(mn)
            mn_t.append(mn / max(DEFAULT_AVAIL_FRACTION_MN, 1e-9))
        return MicronutrientState(
            fe_available=fe_a,
            fe_total=fe_t,
            zn_available=zn_a,
            zn_total=zn_t,
            mn_available=mn_a,
            mn_total=mn_t,
        )
