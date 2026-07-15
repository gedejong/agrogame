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

The mineral-N pool is driven by a **net-mineralisation source** (from soil
organic matter) as well as the crop-uptake and drainage-leaching sinks.
Without the source term the projection was sink-only and trended *opposite*
to the engine in early-season temperate soils, where SOM mineralisation is
the dominant N flux and the real root-zone mineral N accumulates (#353). The
source term mirrors the engine's labile-SOM kinetics so forecast and engine
agree in sign — after #351/#357 the three-pool SOM module is the single
authoritative net-mineralisation source in the engine.

References
----------
* Water-stress coefficient Ks: FAO-56 Irrigation & Drainage Paper
  (Allen et al. 1998), Eq. 84 — Ks scales transpiration linearly once
  root-zone depletion exceeds the readily-available fraction.
* Peak crop N uptake magnitude (~2-4 kg N ha⁻¹ d⁻¹ for maize during rapid
  vegetative growth): Bender et al. 2013, Agronomy Journal 105(1).
* Nitrate mobility / drainage-driven leaching: standard mass-flow argument
  (nitrate travels with drainage water; leaching rises with deep drainage).
* Net N mineralisation from labile SOM: RothC three-pool kinetics
  (Coleman & Jenkinson 1996) with a Q10=2 temperature response and the
  Linn & Doran (1984) moisture response; net rate ~1-3 kg N ha⁻¹ d⁻¹ in
  early-season temperate loam (Stanford & Smith 1972). This mirrors
  ``agrogame.soil.som.pools.ThreePoolSOM`` so the two stay in sign agreement.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from agrogame.atmosphere.et.module import Evapotranspiration
from agrogame.params.phenology import PhenologyStage
from agrogame.soil.som.pools import SOMPoolParams

# --- Heuristic projection constants (documented above) ---------------------
_DEPLETION_FRACTION_P = 0.5  # FAO-56 readily-available fraction (generic p)
_NET_RAD_FRACTION = 0.6  # net radiation as a fraction of incoming shortwave
_PEAK_N_UPTAKE_KG_HA_DAY = 3.0  # maize-scale peak uptake (Bender et al. 2013)
_CANOPY_EXTINCTION_K = 0.6  # Beer's-law light-extinction coefficient
_LEACH_DRAINAGE_HALF_MM = 200.0  # drainage scale for the leaching fraction
_LEACH_MAX_FRACTION = 0.3  # cap on daily mineral-N loss to leaching

# --- Net-mineralisation constants (mirror ThreePoolSOM; see module docstring)
# The rate constant and humification fraction are read from the engine's own
# ``SOMPoolParams`` so any recalibration of the SOM module flows through to the
# forecast automatically and the two cannot silently drift apart.
_SOM_PARAMS = SOMPoolParams()
_SOM_K_LABILE = _SOM_PARAMS.k_labile  # labile SOM decay (1/day), RothC-scale
_SOM_HUMIFICATION_LABILE = _SOM_PARAMS.humification_labile_to_inter
_SOM_Q10_REF_C = 25.0  # RothC Q10=2 reference temperature (°C)
_SOM_MOISTURE_OPTIMUM_WFPS = 0.6  # Linn & Doran (1984) decomposition optimum

# g/m² of N-in-a-layer converts to kg/ha by ×10 (1 g/m² = 10 kg/ha).
_G_M2_TO_KG_HA = 10.0
# theta (m³/m³) over a layer of thickness d (cm) is theta·d·10 mm of water.
_THETA_CM_TO_MM = 10.0

# --- Root-depth growth constants (#366; mirror RootModule) -----------------
# Stage-dependent multiplier on daily root elongation. Duplicated here as a
# small documented constant rather than importing ``RootModule._stage_multiplier``
# to keep the forecast heuristic decoupled from the engine's private method
# (a stale table is a visible, testable diff; a private-method import is a
# hidden coupling). Values mirror ``RootModule._stage_multiplier``'s defaults:
# full elongation while vegetative, tapering through flowering and beyond.
_STAGE_DEPTH_MULTIPLIERS: dict[PhenologyStage, float] = {
    PhenologyStage.EMERGED: 1.0,
    PhenologyStage.VEGETATIVE: 1.0,
    PhenologyStage.FLOWERING: 0.6,
}
_DEFAULT_STAGE_DEPTH_MULTIPLIER = 0.3  # sowing/germination/maturity/senescence


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


def root_zone_som_labile_n_kg_ha(
    som_labile_n: list[float],
    layer_depths_cm: list[float],
    root_depth_cm: float,
) -> float:
    """Sum root-zone labile SOM organic N (kg/ha).

    This is the pool the engine mineralises from after #351/#357 (the labile
    RothC pool dominates the daily net-mineralisation flux). Unlike mineral N,
    SOM pools are already stored per layer in kg/ha, so no g/m² conversion is
    applied — only the root-zone layer weighting.
    """
    fractions = _root_zone_layer_fractions(layer_depths_cm, root_depth_cm)
    total = 0.0
    for i, frac in enumerate(fractions):
        if frac <= 0.0 or i >= len(som_labile_n):
            continue
        total += som_labile_n[i] * frac
    return total


def root_zone_wfps(
    theta: list[float],
    saturation: list[float],
    layer_depths_cm: list[float],
    root_depth_cm: float,
    default: float = _SOM_MOISTURE_OPTIMUM_WFPS,
) -> float:
    """Root-zone-weighted water-filled pore space (theta/saturation), 0-1.

    Feeds the moisture factor of the mineralisation source term. Layers with
    non-positive saturation are skipped; if no rooted layer has usable
    saturation, the neutral ``default`` (the decomposition optimum) is returned
    so the moisture factor neither zeroes out nor inflates the source term.
    """
    fractions = _root_zone_layer_fractions(layer_depths_cm, root_depth_cm)
    weighted = 0.0
    total_frac = 0.0
    for i, frac in enumerate(fractions):
        if frac <= 0.0 or i >= len(theta) or i >= len(saturation):
            continue
        sat = saturation[i]
        if sat <= 0.0:
            continue
        weighted += (theta[i] / sat) * frac
        total_frac += frac
    if total_frac <= 0.0:
        return default
    return weighted / total_frac


def _som_temperature_factor(temp_c: float) -> float:
    """RothC Q10=2 temperature response centred on 25 °C.

    Mirrors ``ThreePoolSOM._temperature_factor`` (Coleman & Jenkinson 1996) so
    the forecast scales mineralisation with temperature identically to the
    engine.
    """
    return float(2.0 ** ((temp_c - _SOM_Q10_REF_C) / 10.0))


def _som_moisture_factor(wfps: float) -> float:
    """Decomposition moisture response, optimum at 60 % WFPS.

    Mirrors ``ThreePoolSOM._moisture_factor`` (Linn & Doran 1984): rises
    linearly to the optimum, then declines toward saturation.
    """
    if wfps <= 0.0:
        return 0.0
    if wfps <= _SOM_MOISTURE_OPTIMUM_WFPS:
        return min(1.0, wfps / _SOM_MOISTURE_OPTIMUM_WFPS)
    return max(0.0, 1.0 - (wfps - _SOM_MOISTURE_OPTIMUM_WFPS) / 0.4)


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


def stage_depth_multiplier(stage: PhenologyStage) -> float:
    """Stage multiplier on daily root elongation (mirrors the engine defaults).

    See ``_STAGE_DEPTH_MULTIPLIERS``. Stages not in the table (sowing,
    germination, maturity, senescence) fall back to the reduced default, matching
    ``RootModule._stage_multiplier``.
    """
    return _STAGE_DEPTH_MULTIPLIERS.get(stage, _DEFAULT_STAGE_DEPTH_MULTIPLIER)


def _advance_root_depth(
    root_depth_cm: float,
    daily_increment_cm: float,
    max_depth_cm: float,
) -> float:
    """Advance root depth one projected day, capped at ``max_depth_cm``.

    Mirrors ``RootModule._update_depth``'s core update
    ``depth = min(max_depth, prev + max(0, growth_rate × stage_mult × cf))`` but
    **omits the engine's constraint factor** ``cf`` (hardpan ×0.2, water-table
    ×0.5, aggregate-penetration ×agg_pen). Over a ~5-day horizon these rarely
    bind, and threading soil-mechanical state into a decision-support heuristic
    is disproportionate; omitting ``cf`` makes the forecast a (mild) *upper*
    bound on deepening, which is the conservative direction for an N-availability
    cue. Documented omission per #366.
    """
    return min(max_depth_cm, root_depth_cm + max(0.0, daily_increment_cm))


def _newly_rooted_mineral_n_kg_ha(
    n_no3: list[float],
    n_nh4: list[float],
    layer_depths_cm: list[float],
    prev_depth_cm: float,
    new_depth_cm: float,
) -> float:
    """Mineral N (kg/ha) pulled into the root zone as it deepens over one day.

    Uses the anchor-day per-layer values: the difference between the root-zone
    mineral N at the new (deeper) depth and at the previous depth. Never
    negative (the zone only deepens).
    """
    prev = root_zone_mineral_n_kg_ha(n_no3, n_nh4, layer_depths_cm, prev_depth_cm)
    new = root_zone_mineral_n_kg_ha(n_no3, n_nh4, layer_depths_cm, new_depth_cm)
    return max(0.0, new - prev)


def project_soil_forecast(
    *,
    available_water_mm: float,
    total_available_water_mm: float,
    mineral_n_kg_ha: float,
    lai: float,
    weather: list[tuple[float, float, float]],
    som_labile_n_kg_ha: float = 0.0,
    root_zone_wfps_frac: float = _SOM_MOISTURE_OPTIMUM_WFPS,
    depletion_fraction_p: float = _DEPLETION_FRACTION_P,
    n_no3_by_layer: list[float] | None = None,
    n_nh4_by_layer: list[float] | None = None,
    layer_depths_cm: list[float] | None = None,
    root_depth_cm: float | None = None,
    root_growth_rate_cm_per_day: float = 0.0,
    root_max_depth_cm: float = float("inf"),
    root_stage_multiplier: float = 1.0,
) -> list[SoilForecastPoint]:
    """Project water-stress and mineral-N ``len(weather)`` days ahead.

    ``weather`` is a list of ``(temp_mean_c, shortwave_mj_m2, rain_mm)`` tuples
    for the forecast days. LAI is held constant over the short horizon (a
    reasonable approximation for a ~5-7 day outlook).

    **Root-zone deepening (#366).** When per-layer mineral N
    (``n_no3_by_layer`` / ``n_nh4_by_layer``), ``layer_depths_cm``,
    ``root_depth_cm`` and a positive ``root_growth_rate_cm_per_day`` are all
    supplied, the root depth is grown each projected day by
    ``root_growth_rate_cm_per_day × root_stage_multiplier`` (capped at
    ``root_max_depth_cm``), mirroring ``RootModule._update_depth`` sans the
    engine's constraint factor (see ``_advance_root_depth``). Each day the newly
    rooted soil contributes its (anchor-day) mineral N to the pool, capturing the
    early-season rise the engine gets from the zone deepening into deeper,
    mineral-N-bearing layers. Omit these params (the default) to keep the prior
    **constant-depth** behaviour, mirroring #363's zero-default source term.
    The water channel does not read any of the deepening inputs and is
    unaffected.

    Mineral N gains a **net-mineralisation source** from the labile SOM pool
    (``som_labile_n_kg_ha``, the root-zone labile organic N) and loses N to
    crop uptake and drainage leaching. ``root_zone_wfps_frac`` sets the moisture
    factor for decomposition and is held constant over the horizon (moisture
    swings slowly relative to temperature; temperature drives the daily
    variation via a Q10=2 response). When ``som_labile_n_kg_ha`` is zero the
    projection is sink-only, preserving the pre-#353 behaviour for callers
    that do not supply an SOM pool.

    Scope: this is a deliberately *conservative* net-mineralisation estimate.
    It reproduces the labile-pool RothC kinetics plus root-zone deepening (#366),
    but still omits source-boosting terms the engine applies: rhizosphere priming
    (up to +50 % on ``k_labile`` in rooted layers — arguably the largest omitted
    contributor) and aggregate protection. The forecast therefore targets *sign*
    agreement with the engine and a bounded magnitude gap, not an exact match.
    """
    et = Evapotranspiration()
    canopy_cover = 1.0 - math.exp(-_CANOPY_EXTINCTION_K * max(0.0, lai))

    available = max(0.0, available_water_mm)
    taw = max(0.0, total_available_water_mm)
    mineral_n = max(0.0, mineral_n_kg_ha)
    labile_n = max(0.0, som_labile_n_kg_ha)
    moist_f = _som_moisture_factor(max(0.0, root_zone_wfps_frac))

    # Bind the deepening inputs as a single narrowed tuple (or None) so the
    # per-day loop stays flat and mypy sees the arrays as non-optional.
    deepen_layers: tuple[list[float], list[float], list[float]] | None = None
    if (
        root_growth_rate_cm_per_day > 0.0
        and n_no3_by_layer is not None
        and n_nh4_by_layer is not None
        and layer_depths_cm is not None
        and root_depth_cm is not None
    ):
        deepen_layers = (n_no3_by_layer, n_nh4_by_layer, layer_depths_cm)
    root_depth = root_depth_cm if root_depth_cm is not None else 0.0
    daily_depth_inc = root_growth_rate_cm_per_day * max(0.0, root_stage_multiplier)

    points: list[SoilForecastPoint] = []
    for temp_mean_c, shortwave_mj_m2, rain_mm in weather:
        ks = water_stress_coefficient(available, taw, depletion_fraction_p)

        # --- Root-zone deepening source (#366): as the zone grows into deeper
        # layers each day, their pre-existing (anchor-day) mineral N enters the
        # pool. Capped at max_depth_cm inside _advance_root_depth.
        if deepen_layers is not None:
            new_depth = _advance_root_depth(
                root_depth, daily_depth_inc, root_max_depth_cm
            )
            mineral_n += _newly_rooted_mineral_n_kg_ha(
                *deepen_layers, root_depth, new_depth
            )
            root_depth = new_depth

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

        # --- Net N mineralisation source (labile SOM pool) -----------------
        # #351/#357 made the three-pool SOM module the single authoritative
        # net-mineralisation source. Mirror its labile-pool kinetics:
        #   decomposed_N = labile_N · k_labile · f(T) · f(moisture)
        # of which the humified fraction stays in SOM and the remainder is
        # released to the mineral pool. Draining the labile pool as it
        # mineralises reproduces the engine's gentle day-to-day deceleration.
        # Without this source the projection trended opposite to the engine in
        # early-season loam (#353). Coleman & Jenkinson (1996); Linn & Doran
        # (1984); net rate ~1-3 kg N/ha/day (Stanford & Smith 1972).
        decomposed_n = labile_n * _SOM_K_LABILE * _som_temperature_factor(temp_mean_c)
        decomposed_n *= moist_f
        labile_n = max(0.0, labile_n - decomposed_n)
        mineral_n += decomposed_n * (1.0 - _SOM_HUMIFICATION_LABILE)

        # Mineral-N sinks: crop uptake (canopy- and stress-scaled) then leaching.
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
