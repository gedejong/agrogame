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
        """Initialize with typical agricultural soil values."""
        return MicronutrientState(
            fe_available=[DEFAULT_TOTAL_FE_PPM * DEFAULT_AVAIL_FRACTION_FE] * n_layers,
            fe_total=[DEFAULT_TOTAL_FE_PPM] * n_layers,
            zn_available=[DEFAULT_TOTAL_ZN_PPM * DEFAULT_AVAIL_FRACTION_ZN] * n_layers,
            zn_total=[DEFAULT_TOTAL_ZN_PPM] * n_layers,
            mn_available=[DEFAULT_TOTAL_MN_PPM * DEFAULT_AVAIL_FRACTION_MN] * n_layers,
            mn_total=[DEFAULT_TOTAL_MN_PPM] * n_layers,
        )
