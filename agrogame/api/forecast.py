"""Soil/crop forecast projection for decision support (#318).

The game's ``/forecast`` surface historically exposed weather only. This
module adds a *lightweight, transparent* projection of the two state
variables that most often drive a player's next action: root-zone plant
**water-stress** and **mineral-nitrogen** availability.

This is deliberately a cheap heuristic projector, not a shadow run of the
full Richards/RothC engine. It advances a single-bucket root-zone water
balance and a mineral-N pool over the forecast horizon using the upcoming
weather. It is intended for "what is likely to happen if I do nothing"
guidance, and is labelled as an estimate in the UI.

References
----------
* Water-stress coefficient Ks: FAO-56 Irrigation & Drainage Paper
  (Allen et al. 1998), Eq. 84 — Ks scales transpiration linearly once
  root-zone depletion exceeds the readily-available fraction.
* Peak crop N uptake magnitude (~2-4 kg N ha⁻¹ d⁻¹ for maize during rapid
  vegetative growth): Bender et al. 2013, Agronomy Journal 105(1).
* Nitrate mobility / drainage-driven leaching: standard mass-flow argument
  (nitrate travels with drainage water; leaching rises with deep drainage).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from agrogame.atmosphere.et.module import Evapotranspiration

# --- Heuristic projection constants (documented above) ---------------------
_DEPLETION_FRACTION_P = 0.5  # FAO-56 readily-available fraction (generic p)
_NET_RAD_FRACTION = 0.6  # net radiation as a fraction of incoming shortwave
_PEAK_N_UPTAKE_KG_HA_DAY = 3.0  # maize-scale peak uptake (Bender et al. 2013)
_CANOPY_EXTINCTION_K = 0.6  # Beer's-law light-extinction coefficient
_LEACH_DRAINAGE_HALF_MM = 200.0  # drainage scale for the leaching fraction
_LEACH_MAX_FRACTION = 0.3  # cap on daily mineral-N loss to leaching

# g/m² of N-in-a-layer converts to kg/ha by ×10 (1 g/m² = 10 kg/ha).
_G_M2_TO_KG_HA = 10.0
# theta (m³/m³) over a layer of thickness d (cm) is theta·d·10 mm of water.
_THETA_CM_TO_MM = 10.0


@dataclass(frozen=True)
class SoilForecastPoint:
    """One projected day of soil/crop decision-support state."""

    water_stress: float  # FAO-56 Ks proxy: 1.0 = no stress, 0.0 = severe
    mineral_n_kg_ha: float  # projected root-zone mineral N (NO3 + NH4)


def _root_zone_layer_fractions(
    layer_depths_cm: list[float], root_depth_cm: float
) -> list[float]:
    """Fraction of each layer that lies within the root zone (0..1).

    The final rooted layer is partially weighted when roots stop partway
    through it, so a shallow root system does not over-count deep water/N.
    """
    fractions: list[float] = []
    top_cm = 0.0
    for depth in layer_depths_cm:
        bottom_cm = top_cm + depth
        if root_depth_cm <= top_cm:
            fractions.append(0.0)
        elif root_depth_cm >= bottom_cm:
            fractions.append(1.0)
        else:
            fractions.append((root_depth_cm - top_cm) / depth if depth > 0 else 0.0)
        top_cm = bottom_cm
    return fractions


def root_zone_water_mm(
    theta: list[float],
    layer_depths_cm: list[float],
    field_capacity: list[float],
    wilting_point: list[float],
    root_depth_cm: float,
) -> tuple[float, float]:
    """Return (available_water_mm, total_available_water_mm) in the root zone.

    Available water is water held above wilting point; total available water
    (TAW) is the field-capacity-minus-wilting-point holding capacity.
    """
    fractions = _root_zone_layer_fractions(layer_depths_cm, root_depth_cm)
    available = 0.0
    taw = 0.0
    for i, frac in enumerate(fractions):
        if frac <= 0.0:
            continue
        depth_mm = layer_depths_cm[i] * _THETA_CM_TO_MM * frac
        aw_theta = max(0.0, theta[i] - wilting_point[i])
        taw_theta = max(0.0, field_capacity[i] - wilting_point[i])
        available += aw_theta * depth_mm
        taw += taw_theta * depth_mm
    return available, taw


def root_zone_mineral_n_kg_ha(
    n_no3: list[float],
    n_nh4: list[float],
    layer_depths_cm: list[float],
    root_depth_cm: float,
) -> float:
    """Sum root-zone mineral N (NO3 + NH4), converting g/m² layers to kg/ha."""
    fractions = _root_zone_layer_fractions(layer_depths_cm, root_depth_cm)
    total_g_m2 = 0.0
    for i, frac in enumerate(fractions):
        if frac <= 0.0:
            continue
        total_g_m2 += (n_no3[i] + n_nh4[i]) * frac
    return total_g_m2 * _G_M2_TO_KG_HA


def water_stress_coefficient(
    available_water_mm: float,
    total_available_water_mm: float,
    depletion_fraction_p: float = _DEPLETION_FRACTION_P,
) -> float:
    """FAO-56 transpiration stress coefficient Ks (Allen et al. 1998, Eq. 84).

    Ks = 1 while root-zone depletion stays within the readily-available
    fraction (p·TAW); below that it declines linearly to 0 at wilting point.
    Returned on the app's convention (1 = no stress, 0 = severe).
    """
    if total_available_water_mm <= 0.0:
        return 1.0
    readily_available = (1.0 - depletion_fraction_p) * total_available_water_mm
    if readily_available <= 0.0:
        return 1.0 if available_water_mm > 0.0 else 0.0
    ks = available_water_mm / readily_available
    return max(0.0, min(1.0, ks))


def project_soil_forecast(
    *,
    available_water_mm: float,
    total_available_water_mm: float,
    mineral_n_kg_ha: float,
    lai: float,
    weather: list[tuple[float, float, float]],
    depletion_fraction_p: float = _DEPLETION_FRACTION_P,
) -> list[SoilForecastPoint]:
    """Project water-stress and mineral-N ``len(weather)`` days ahead.

    ``weather`` is a list of ``(temp_mean_c, shortwave_mj_m2, rain_mm)`` tuples
    for the forecast days. LAI and root depth are held constant over the short
    horizon (a reasonable approximation for a ~5-7 day outlook).
    """
    et = Evapotranspiration()
    canopy_cover = 1.0 - math.exp(-_CANOPY_EXTINCTION_K * max(0.0, lai))

    available = max(0.0, available_water_mm)
    taw = max(0.0, total_available_water_mm)
    mineral_n = max(0.0, mineral_n_kg_ha)

    points: list[SoilForecastPoint] = []
    for temp_mean_c, shortwave_mj_m2, rain_mm in weather:
        ks = water_stress_coefficient(available, taw, depletion_fraction_p)

        # Actual ET: transpiration is throttled by Ks under canopy; the
        # uncovered fraction keeps a reference-rate evaporative demand.
        et0 = et.priestley_taylor(temp_mean_c, _NET_RAD_FRACTION * shortwave_mj_m2)
        et_actual = et0 * (1.0 - canopy_cover * (1.0 - ks))

        # Root-zone water bucket: rain in, ET out, excess above TAW drains.
        water_after = available + max(0.0, rain_mm) - et_actual
        if taw > 0.0:
            drainage = max(0.0, water_after - taw)
            available = max(0.0, min(water_after, taw))
        else:
            drainage = max(0.0, water_after)
            available = max(0.0, water_after)

        # Mineral-N: crop uptake (canopy- and stress-scaled) then leaching.
        uptake = _PEAK_N_UPTAKE_KG_HA_DAY * canopy_cover * ks
        mineral_n = max(0.0, mineral_n - uptake)
        leach_fraction = min(
            _LEACH_MAX_FRACTION, drainage / (drainage + _LEACH_DRAINAGE_HALF_MM)
        )
        mineral_n = max(0.0, mineral_n - mineral_n * leach_fraction)

        points.append(
            SoilForecastPoint(
                water_stress=round(ks, 3),
                mineral_n_kg_ha=round(mineral_n, 1),
            )
        )
    return points
