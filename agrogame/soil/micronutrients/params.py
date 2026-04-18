"""Immutable micronutrient parameters."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.soil.micronutrients.constants import (
    CRITICAL_FE_PPM,
    CRITICAL_MN_PPM,
    CRITICAL_ZN_PPM,
    DEFAULT_DEMAND_FE_G_HA,
    DEFAULT_DEMAND_MN_G_HA,
    DEFAULT_DEMAND_ZN_G_HA,
    TOXIC_FE_PPM,
    TOXIC_MN_PPM,
    TOXIC_ZN_PPM,
)


@dataclass(frozen=True)
class MicronutrientParams:
    """Parameters for micronutrient cycling.

    Attributes:
        demand_fe_g_ha: Season total Fe demand (g/ha).
        demand_zn_g_ha: Season total Zn demand (g/ha).
        demand_mn_g_ha: Season total Mn demand (g/ha).
        critical_fe_ppm: Below this, deficiency stress.
        critical_zn_ppm: Below this, deficiency stress.
        critical_mn_ppm: Below this, deficiency stress.
        toxic_fe_ppm: Above this, toxicity stress.
        toxic_zn_ppm: Above this, toxicity stress.
        toxic_mn_ppm: Above this, toxicity stress.
        om_complexation_factor: Fraction of available pool complexed per unit SOM.
        season_days: Expected season length for daily demand scaling.
    """

    demand_fe_g_ha: float = DEFAULT_DEMAND_FE_G_HA
    demand_zn_g_ha: float = DEFAULT_DEMAND_ZN_G_HA
    demand_mn_g_ha: float = DEFAULT_DEMAND_MN_G_HA
    critical_fe_ppm: float = CRITICAL_FE_PPM
    critical_zn_ppm: float = CRITICAL_ZN_PPM
    critical_mn_ppm: float = CRITICAL_MN_PPM
    toxic_fe_ppm: float = TOXIC_FE_PPM
    toxic_zn_ppm: float = TOXIC_ZN_PPM
    toxic_mn_ppm: float = TOXIC_MN_PPM
    om_complexation_factor: float = 0.001
    season_days: float = 150.0


@dataclass(frozen=True)
class RedoxMicronutrientParams:
    """Redox-driven Fe/Mn pool transitions (#216).

    When soil Eh falls below an element-specific threshold, a fraction
    of the sorbed/mineral pool (implicit = total - available) moves to
    the available pool per day, scaled by reducing severity. When Eh
    rises above the re-oxidation threshold, available precipitates
    back into sorbed at a slower rate (Patrick & Reddy 1976).

    Attributes:
        fe_reduction_eh_mv: Eh threshold below which Fe³⁺ → Fe²⁺.
            Ref: Patrick & Reddy 1976 — Fe reduction zone.
        mn_reduction_eh_mv: Eh threshold below which Mn⁴⁺ → Mn²⁺.
            Ref: Stumm & Morgan 1996 — Mn reduces earlier than Fe.
        reoxidation_eh_mv: Eh threshold above which Fe²⁺/Mn²⁺ precipitate.
        reduction_rate_per_day: Base fraction moved from sorbed to
            available at maximum reducing severity (1/day).
        reoxidation_rate_per_day: Base fraction moved from available back
            to sorbed at full re-oxidation (1/day). Asymmetrically
            slower than reduction — precipitation kinetics lag
            dissolution (Patrick & Reddy 1976).
        severity_span_mv: Eh span below/above threshold that produces
            full-strength severity (linear ramp 0 → 1).
    """

    fe_reduction_eh_mv: float = 100.0
    mn_reduction_eh_mv: float = 200.0
    reoxidation_eh_mv: float = 300.0
    reduction_rate_per_day: float = 0.02
    reoxidation_rate_per_day: float = 0.005
    severity_span_mv: float = 200.0
