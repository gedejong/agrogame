"""Soil/crop forecast projection for decision support (#318, #689).

The ``/forecast`` surface projects the two quantities that most often drive a
player's next action: the crop's water stress and the root-zone mineral N. It
does not shadow-run the engine. It advances a root-zone water bucket and a
mineral-N pool over the forecast weather, and every flux it computes calls the
engine's own function, so forecast and engine cannot drift apart (#689).

Water, per day, in the engine's phase order (water, then et; ADR-010):

* ET0 by Priestley & Taylor (1972) on Rn = 0.6 Rs (ADR-014), split into
  potential E and T by Beer's law (``Evapotranspiration.potential_components``);
  the anchor LAI is held over the horizon.
* Rain of ``EtParams.wetting_reset_threshold_mm`` or more resets the Ritchie
  stage clock, as ``ETRuntime._update_wetting_and_residue`` does.
* SCS curve-number runoff (USDA-SCS NEH-4) with the engine's layer-0 texture CN.
  Water above the bucket's total available water (TAW) drains.
* Soil evaporation is Ritchie's (1972) two-stage drying of the topsoil, residue
  adjusted (``Evapotranspiration.ritchie_evaporation`` and
  ``residue_adjusted_params``).
* Transpiration is Tp × Ks with the crop's p (FAO-56, Allen et al. 1998,
  Eq. 82-84, Table 22). The row reports Ta/Tp, the quantity the Water gauge
  reads (``WaterStressComputed.stress``).

Mineral N, in kg/ha as the engine holds its pools, per day: root-zone deepening
(#366/#383); the anchor day's SOM net mineralisation, scaled by the engine's
Q10 = 2 temperature response (Coleman & Jenkinson 1996); the anchor day's plant N
uptake; and NO3 leaching by the engine's mixing-cell rule
(``NitrogenCycle._on_water_drained``; Burns 1974, J. Soil Sci. 25:155; CERES-N,
Godwin & Singh 1998). Holding the anchor day's fluxes over the horizon is the
persistence forecast, the standard reference forecast (Wilks 2011, Statistical
Methods in the Atmospheric Sciences, 3rd ed.).
"""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.atmosphere.et.module import Evapotranspiration
from agrogame.atmosphere.et.params import EtParams
from agrogame.atmosphere.et.types import EtState
from agrogame.params.phenology import PhenologyStage
from agrogame.soil.water.scs import scs_runoff_mm
from agrogame.weather.constants import NET_RAD_FRACTION

# FAO-56 depletion fraction p for a caller with no crop: "a value of 0.50 for p
# is commonly used for many crops" (Allen et al. 1998, ch. 8, readily available
# water).
# The route passes the anchor crop's own Table 22 p.
_DEPLETION_FRACTION_P = 0.5
_SOM_Q10_REF_C = 25.0  # RothC Q10=2 reference temperature (°C), as ThreePoolSOM

# theta (m³/m³) over a layer of thickness d (cm) is theta·d·10 mm of water.
_THETA_CM_TO_MM = 10.0

# --- Root-depth growth constants (#366; mirror RootModule) -----------------
# Stage-dependent multiplier on daily root elongation. Duplicated here as a
# small documented constant rather than importing ``RootModule._stage_multiplier``
# to keep the forecast heuristic decoupled from the engine's private method
# (a stale table is a visible, testable diff; a private-method import is a
# hidden coupling). Values mirror the *default* branch of
# ``RootModule._stage_multiplier``: full elongation while vegetative, tapering
# through flowering and grain fill, and a hard stop at maturity (#539). Crop-level
# overrides (``RootParams.stage_multipliers``, wired via ``plant/roots/factory.py``)
# take precedence for every stage except MATURITY — see
# ``stage_depth_multiplier``'s ``overrides`` argument.
_STAGE_DEPTH_MULTIPLIERS: dict[PhenologyStage, float] = {
    PhenologyStage.EMERGED: 1.0,
    PhenologyStage.VEGETATIVE: 1.0,
    PhenologyStage.FLOWERING: 0.6,
}
_DEFAULT_STAGE_DEPTH_MULTIPLIER = 0.3  # planted/grain fill


@dataclass(frozen=True)
class SoilForecastPoint:
    """One projected day of soil/crop decision-support state."""

    water_stress: float  # the day's projected Ta/Tp: 1.0 = no stress, 0.0 = severe
    mineral_n_kg_ha: float  # projected root-zone mineral N (NO3 + NH4), kg/ha
    # Available over total available water at the end of the day, capped at 1
    # (#689); internal until #691 shows it as the Root zone gauge.
    root_zone_water_fraction: float


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


def root_zone_sum(
    per_layer: list[float],
    layer_depths_cm: list[float],
    root_depth_cm: float,
) -> float:
    """Root-zone total of a per-layer quantity, the last rooted layer partial.

    A layer contributes its rooted fraction; layers with no value (a shorter
    list, such as an absent SOM module's) contribute nothing.
    """
    fractions = _root_zone_layer_fractions(layer_depths_cm, root_depth_cm)
    return sum(v * f for v, f in zip(per_layer, fractions, strict=False) if f > 0.0)


def root_zone_mineral_n_kg_ha(
    n_no3: list[float],
    n_nh4: list[float],
    layer_depths_cm: list[float],
    root_depth_cm: float,
) -> float:
    """Root-zone mineral N (NO3 + NH4), kg/ha.

    The engine's pools are kg/ha per layer (``SoilNitrogenState``), so the
    root-zone total needs only the layer weighting (#689 removed a ×10 that read
    them as g/m²).
    """
    totals = [a + b for a, b in zip(n_no3, n_nh4, strict=True)]
    return root_zone_sum(totals, layer_depths_cm, root_depth_cm)


def _som_temperature_factor(temp_c: float) -> float:
    """RothC Q10=2 temperature response centred on 25 °C.

    Mirrors ``ThreePoolSOM._temperature_factor`` (Coleman & Jenkinson 1996) so
    the forecast scales mineralisation with temperature identically to the
    engine.
    """
    return float(2.0 ** ((temp_c - _SOM_Q10_REF_C) / 10.0))


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


def stage_depth_multiplier(
    stage: PhenologyStage,
    overrides: dict[PhenologyStage, float] | None = None,
) -> float:
    """Stage multiplier on daily root elongation (mirrors ``RootModule``).

    Mirrors ``RootModule._stage_multiplier`` **including the crop-override
    branch**: when ``overrides`` (the crop's ``RootParams.stage_multipliers``,
    wired into the engine via ``plant/roots/factory.py``) contains ``stage``, its
    value wins (clamped ≥ 0). Otherwise the default table
    (``_STAGE_DEPTH_MULTIPLIERS``) applies, with stages not in it (planted,
    grain fill) falling back to the reduced default. MATURITY is a hard stop at
    0.0 that no override lifts, as in the engine (#539).

    Threading ``overrides`` through keeps the forecast's depth projection in step
    with any crop that customises its stage table; no shipped preset sets one
    today, but a future preset would otherwise silently diverge from the engine.
    """
    if stage is PhenologyStage.MATURITY:
        return 0.0
    if overrides and stage in overrides:
        return max(0.0, overrides[stage])
    return _STAGE_DEPTH_MULTIPLIERS.get(stage, _DEFAULT_STAGE_DEPTH_MULTIPLIER)


def _advance_root_depth(
    root_depth_cm: float,
    daily_increment_cm: float,
    max_depth_cm: float,
) -> float:
    """Advance root depth one projected day, capped at ``max_depth_cm``.

    Mirrors ``RootModule._update_depth``'s core update
    ``depth = min(max_depth, prev + max(0, growth_rate × stage_mult × cf))``.
    The caller folds the **aggregate-penetration** channel of the engine's
    constraint factor ``cf`` into ``daily_increment_cm`` (#383; see
    ``project_soil_forecast``), so the increment reaching this function already
    carries agg-penetration. That channel is a single top-layer, depth-independent
    scalar held constant over the horizon, which *mirrors* the engine exactly.

    Still intentionally omitted are the engine's two **depth-triggered**
    constraint multipliers (hardpan ×0.2 once ``depth ≥ hardpan_cm``; water-table
    ×0.5 once ``depth ≥ water_table_cm``). On the pinned no-action horizon neither
    binds, so they contribute nothing to magnitude, and threading depth-triggered
    soil-mechanical state into a decision-support heuristic is disproportionate
    (#383). The residual — a projected zone that deepens past a hardpan/water-table
    the engine would have hit — is a documented, rarely-binding divergence,
    symmetric with how the anchor-day fluxes and per-layer MWD are held constant.
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


@dataclass
class _Bucket:
    """Root-zone water bucket in mm of water above wilting point (#689)."""

    available: float
    taw: float
    topsoil: float  # layer 0's share, the store soil evaporation draws on
    topsoil_capacity: float
    topsoil_root_fraction: float  # share of transpiration drawn from layer 0
    cumulative_evap_mm: float  # the Ritchie stage clock


@dataclass(frozen=True)
class _WaterDrivers:
    """Water inputs held at their anchor values over the horizon."""

    et: Evapotranspiration
    lai: float
    curve_number: int | None
    stage1_limit_mm: float
    ritchie_coef: float
    depletion_fraction_p: float


def _water_day(
    b: _Bucket, w: _WaterDrivers, temp_mean_c: float, shortwave: float, rain: float
) -> tuple[float, float]:
    """Advance the bucket one day; return (drainage mm, Ta/Tp).

    The water phase (runoff, infiltration, drainage) runs before the et phase
    (wetting reset, evaporation, transpiration), as in the engine (ADR-010).
    """
    et = w.et
    rain = max(0.0, rain)
    runoff = scs_runoff_mm(rain, w.curve_number) if w.curve_number is not None else 0.0
    b.topsoil = min(b.topsoil_capacity, b.topsoil + rain - runoff)
    b.available += rain - runoff
    drainage = max(0.0, b.available - b.taw)
    b.available = min(b.available, b.taw)

    if rain >= et.params.wetting_reset_threshold_mm:
        b.cumulative_evap_mm = 0.0
    et0 = et.priestley_taylor(temp_mean_c, NET_RAD_FRACTION * shortwave)
    comps = et.potential_components(et0, w.lai)
    clock = EtState(cumulative_evap_mm=b.cumulative_evap_mm)
    evap = et.ritchie_evaporation(
        clock,
        comps.potential_evap_mm,
        min(b.topsoil, b.available),
        stage1_limit_mm=w.stage1_limit_mm,
        ritchie_coef=w.ritchie_coef,
    )
    b.cumulative_evap_mm = clock.cumulative_evap_mm
    b.topsoil -= evap
    b.available -= evap

    tp = comps.potential_transp_mm
    ks = water_stress_coefficient(b.available, b.taw, w.depletion_fraction_p)
    transp = min(tp * ks, b.available)
    b.topsoil = max(0.0, b.topsoil - transp * b.topsoil_root_fraction)
    b.available -= transp
    return drainage, (transp / tp if tp > 0.0 else 1.0)


@dataclass
class _NPool:
    """Root-zone mineral N (kg/ha) and the root depth that bounds the zone."""

    mineral_n: float
    root_depth: float


@dataclass(frozen=True)
class _NDrivers:
    """Mineral-N inputs held at their anchor values over the horizon (#689)."""

    deepen_layers: tuple[list[float], list[float], list[float]] | None
    daily_depth_inc: float
    max_depth_cm: float
    mineralization_kg_ha_day: float
    anchor_temp_c: float | None
    uptake_kg_ha_day: float
    no3_share: float
    fc_storage_mm: float


def _n_day(n: _NPool, d: _NDrivers, temp_mean_c: float, drainage_mm: float) -> None:
    """Advance mineral N one day: deepening, source, uptake, then leaching."""
    if d.deepen_layers is not None:
        new_depth = _advance_root_depth(n.root_depth, d.daily_depth_inc, d.max_depth_cm)
        n.mineral_n += _newly_rooted_mineral_n_kg_ha(
            *d.deepen_layers, n.root_depth, new_depth
        )
        n.root_depth = new_depth
    temp_f = 1.0
    if d.anchor_temp_c is not None:
        temp_f = _som_temperature_factor(temp_mean_c) / _som_temperature_factor(
            d.anchor_temp_c
        )
    n.mineral_n += d.mineralization_kg_ha_day * temp_f
    n.mineral_n = max(0.0, n.mineral_n - d.uptake_kg_ha_day)
    if drainage_mm > 0.0:
        # Mixing cell: the drainage carries D / W_fc of the zone's NO3.
        moved = 1.0
        if d.fc_storage_mm > 0.0:
            moved = min(1.0, drainage_mm / d.fc_storage_mm)
        n.mineral_n -= n.mineral_n * d.no3_share * moved


def _deepening_layers(
    growth_rate_cm_per_day: float,
    n_no3_by_layer: list[float] | None,
    n_nh4_by_layer: list[float] | None,
    layer_depths_cm: list[float] | None,
    root_depth_cm: float | None,
) -> tuple[list[float], list[float], list[float]] | None:
    """The deepening inputs as one narrowed tuple, or None to hold the depth.

    Binding them once keeps the per-day step flat and lets mypy see the arrays
    as non-optional (#366).
    """
    if (
        growth_rate_cm_per_day > 0.0
        and n_no3_by_layer is not None
        and n_nh4_by_layer is not None
        and layer_depths_cm is not None
        and root_depth_cm is not None
    ):
        return n_no3_by_layer, n_nh4_by_layer, layer_depths_cm
    return None


def project_soil_forecast(
    *,
    available_water_mm: float,
    total_available_water_mm: float,
    mineral_n_kg_ha: float,
    lai: float,
    weather: list[tuple[float, float, float]],
    depletion_fraction_p: float | None = None,
    topsoil_available_mm: float | None = None,
    topsoil_capacity_mm: float | None = None,
    topsoil_root_fraction: float = 1.0,
    cumulative_evap_mm: float = 0.0,
    residue_cover_fraction: float = 0.0,
    curve_number: int | None = None,
    et_params: EtParams | None = None,
    som_mineralization_kg_ha_day: float = 0.0,
    anchor_temp_c: float | None = None,
    plant_n_uptake_kg_ha_day: float = 0.0,
    no3_share: float = 1.0,
    root_zone_fc_mm: float | None = None,
    n_no3_by_layer: list[float] | None = None,
    n_nh4_by_layer: list[float] | None = None,
    layer_depths_cm: list[float] | None = None,
    root_depth_cm: float | None = None,
    root_growth_rate_cm_per_day: float = 0.0,
    root_max_depth_cm: float = float("inf"),
    root_stage_multiplier: float = 1.0,
    root_penetration_factor: float = 1.0,
    crop_n_uptake: bool = True,
) -> list[SoilForecastPoint]:
    """Project water stress and root-zone mineral N ``len(weather)`` days ahead.

    ``weather`` holds ``(temp_mean_c, shortwave_mj_m2, rain_mm)`` per forecast
    day. The anchor LAI is held over the short horizon.

    **Water (#689).** ``available_water_mm`` and ``total_available_water_mm``
    describe the bucket: the route floors its depth at layer 0, as
    ``_root_zone_water_fraction`` does. ``topsoil_available_mm`` and
    ``topsoil_capacity_mm`` are layer 0's available water and FC − WP storage;
    ``None`` makes the topsoil the whole bucket. ``topsoil_root_fraction`` is the
    share of transpiration taken from layer 0 (``root_state.layer_fractions[0]``).
    ``cumulative_evap_mm`` and ``residue_cover_fraction`` are the ``ETRuntime``'s
    stage clock and residue cover; ``curve_number`` is the engine's layer-0 CN
    (``None``: no runoff). ``depletion_fraction_p`` is the crop's FAO-56 p
    (``None``: the generic 0.5, for a caller with no crop).

    **Mineral N (#689).** All in kg/ha. ``som_mineralization_kg_ha_day`` is the
    root-zone total of the engine's ``som_mineralized_n_by_layer`` on the anchor
    day, scaled each day by 2^((T − ``anchor_temp_c``)/10) (``None``: unscaled).
    ``plant_n_uptake_kg_ha_day`` is the anchor day's plant N uptake, dropped when
    ``crop_n_uptake`` is False (a crop at MATURITY takes up no N; #539).
    Leaching removes ``no3_share`` × min(1, D / ``root_zone_fc_mm``) of the pool,
    where D is the bucket's drainage and ``root_zone_fc_mm`` its field-capacity
    storage (``None``: the TAW, a lower bound on it); with no FC storage, drainage
    flushes all the NO3.

    **Root-zone deepening (#366/#383).** When the per-layer mineral N
    (``n_no3_by_layer`` / ``n_nh4_by_layer``), ``layer_depths_cm``,
    ``root_depth_cm`` and a positive ``root_growth_rate_cm_per_day`` are all
    supplied, the root depth grows each projected day by
    ``root_growth_rate_cm_per_day × root_stage_multiplier × root_penetration_factor``
    (capped at ``root_max_depth_cm``), mirroring ``RootModule._update_depth``, and
    the newly rooted soil adds its anchor-day mineral N. Omit them to hold the
    depth constant. ``root_penetration_factor`` is the engine's
    aggregate-penetration constraint, ``root_penetration_factor(agg_state.mwd(0))``,
    a single top-layer scalar in [0, 1] that held constant mirrors the engine
    exactly; the depth-triggered hardpan and water-table multipliers are not
    threaded (see ``_advance_root_depth``). The water channel reads none of the
    deepening inputs.
    """
    et = Evapotranspiration(et_params)
    stage1, coef = et.residue_adjusted_params(
        et.params.stage1_limit_mm,
        et.params.ritchie_coef,
        residue_cover_fraction,
        et.params.residue_stage1_reduction,
        et.params.residue_stage2_reduction,
    )
    available = max(0.0, available_water_mm)
    taw = max(0.0, total_available_water_mm)
    bucket = _Bucket(
        available=available,
        taw=taw,
        topsoil=available if topsoil_available_mm is None else topsoil_available_mm,
        topsoil_capacity=taw if topsoil_capacity_mm is None else topsoil_capacity_mm,
        topsoil_root_fraction=topsoil_root_fraction,
        cumulative_evap_mm=cumulative_evap_mm,
    )
    water = _WaterDrivers(
        et=et,
        lai=lai,
        curve_number=curve_number,
        stage1_limit_mm=stage1,
        ritchie_coef=coef,
        depletion_fraction_p=(
            _DEPLETION_FRACTION_P
            if depletion_fraction_p is None
            else depletion_fraction_p
        ),
    )

    deepen_layers = _deepening_layers(
        root_growth_rate_cm_per_day,
        n_no3_by_layer,
        n_nh4_by_layer,
        layer_depths_cm,
        root_depth_cm,
    )
    # Fold the aggregate-penetration constraint (#383) into the daily increment
    # once: clamped to [0, 1], the 1.0 default reproduces the cf-omitted path.
    cf = max(0.0, min(1.0, root_penetration_factor))
    nitrogen = _NDrivers(
        deepen_layers=deepen_layers,
        daily_depth_inc=root_growth_rate_cm_per_day
        * max(0.0, root_stage_multiplier)
        * cf,
        max_depth_cm=root_max_depth_cm,
        mineralization_kg_ha_day=som_mineralization_kg_ha_day,
        anchor_temp_c=anchor_temp_c,
        uptake_kg_ha_day=plant_n_uptake_kg_ha_day if crop_n_uptake else 0.0,
        no3_share=no3_share,
        fc_storage_mm=taw if root_zone_fc_mm is None else root_zone_fc_mm,
    )
    pool = _NPool(
        mineral_n=max(0.0, mineral_n_kg_ha),
        root_depth=root_depth_cm if root_depth_cm is not None else 0.0,
    )

    points: list[SoilForecastPoint] = []
    for temp_mean_c, shortwave_mj_m2, rain_mm in weather:
        drainage, ta_over_tp = _water_day(
            bucket, water, temp_mean_c, shortwave_mj_m2, rain_mm
        )
        _n_day(pool, nitrogen, temp_mean_c, drainage)
        points.append(
            SoilForecastPoint(
                water_stress=round(ta_over_tp, 3),
                mineral_n_kg_ha=round(pool.mineral_n, 2),
                root_zone_water_fraction=(
                    round(bucket.available / taw, 3) if taw > 0.0 else 0.0
                ),
            )
        )
    return points
