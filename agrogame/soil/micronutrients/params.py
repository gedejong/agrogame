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
