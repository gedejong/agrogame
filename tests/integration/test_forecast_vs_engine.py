"""Forecast-vs-engine sign-agreement test for the mineral-N projection (#353).

The decision-support forecast (:mod:`agrogame.api.forecast`) must trend the
same direction as the real engine over a short no-action horizon. Before #353
the projection was sink-only (crop uptake + drainage leaching) and trended
*down* while the engine's root-zone mineral N trended *up* — a wrong-sign
indicator that would cue a player to fertilise exactly when soil N is building.

This test establishes maize on ``loam_temperate`` for ~20 days, then compares a
5-day forecast against 5 real no-action engine steps on the *same* weather. The
core assertion is sign agreement; exact magnitude is not asserted because the
engine's steeper rise reflects several source-boosting terms the heuristic
forecast deliberately omits: rhizosphere priming (up to +50 % on ``k_labile``
in rooted layers, arguably the largest contributor), aggregate protection, and
a root-zone-geometry effect (the rooting depth deepens into more soil each day
while the constant-root-depth projector holds it fixed).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.api.forecast import (
    _root_zone_layer_fractions,
    project_soil_forecast,
    root_zone_mineral_n_kg_ha,
    root_zone_som_labile_n_kg_ha,
    root_zone_water_mm,
    stage_depth_multiplier,
)
from agrogame.plant.presets import _load_crop_presets_cached, load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.aggregation.dynamic_state import root_penetration_factor
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import (
    _load_climate_presets_cached,
    load_climate_presets,
)

_ESTABLISH_DAYS = 20
_HORIZON_DAYS = 5


def _build(days: int, seed: int = 42) -> tuple[FullSimulationOrchestrator, list]:
    _load_crop_presets_cached.cache_clear()
    _load_climate_presets_cached.cache_clear()
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    profile = load_soil_presets(Path("soils/presets.yaml")).soils["loam_temperate"]
    crop = crops.get_preset("maize", "netherlands_temperate")
    climate = climates.climates["netherlands_temperate"]
    series = SyntheticWeatherGenerator(climate, seed=seed).generate(
        days, date(2024, 4, 1)
    )
    orch = FullSimulationOrchestrator(
        profile, crop=crop, latitude_deg=climate.latitude_deg
    )
    return orch, series.records


def _step(orch: FullSimulationOrchestrator, rec) -> None:
    orch.step_day(
        drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
        tmin_c=rec.tmin_c,
        tmax_c=rec.tmax_c,
        shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
        sim_date=rec.day,
    )


def _root_zone_mineral_n(orch: FullSimulationOrchestrator) -> float:
    layers = orch.profile.layers
    depths = [ly.depth_cm for ly in layers]
    rd = orch.root_state.current_depth_cm
    return root_zone_mineral_n_kg_ha(
        list(orch.n_state.no3), list(orch.n_state.nh4), depths, rd
    )


def _forecast_inputs(orch: FullSimulationOrchestrator) -> dict[str, float]:
    layers = orch.profile.layers
    depths = [ly.depth_cm for ly in layers]
    rd = orch.root_state.current_depth_cm
    available, taw = root_zone_water_mm(
        list(orch.water_state.theta),
        depths,
        [ly.field_capacity for ly in layers],
        [ly.wilting_point for ly in layers],
        rd,
    )
    labile_n = [ly.labile.n_kg_ha for ly in orch.som.state.layers]
    fracs = _root_zone_layer_fractions(depths, rd)
    theta = orch.water_state.theta
    num = den = 0.0
    for i, frac in enumerate(fracs):
        sat = layers[i].saturation
        if frac <= 0.0 or sat <= 0.0 or i >= len(theta):
            continue
        num += (theta[i] / sat) * frac
        den += frac
    wfps = num / den if den > 0.0 else 0.6
    return {
        "available_water_mm": available,
        "total_available_water_mm": taw,
        "mineral_n_kg_ha": _root_zone_mineral_n(orch),
        "lai": orch.canopy.state.lai,
        "som_labile_n_kg_ha": root_zone_som_labile_n_kg_ha(labile_n, depths, rd),
        "root_zone_wfps_frac": wfps,
    }


def test_forecast_mineral_n_trend_agrees_with_engine_sign() -> None:
    """Early-season loam maize: forecast N and engine N must both rise."""
    orch, records = _build(_ESTABLISH_DAYS + _HORIZON_DAYS)
    for rec in records[:_ESTABLISH_DAYS]:
        _step(orch, rec)

    inputs = _forecast_inputs(orch)
    anchor_n = inputs["mineral_n_kg_ha"]
    window = records[_ESTABLISH_DAYS : _ESTABLISH_DAYS + _HORIZON_DAYS]
    weather = [
        ((r.tmin_c + r.tmax_c) / 2.0, r.shortwave_mj_m2 or 12.0, r.precip_mm or 0.0)
        for r in window
    ]

    projection = project_soil_forecast(weather=weather, **inputs)
    forecast_end = projection[-1].mineral_n_kg_ha
    forecast_delta = forecast_end - anchor_n

    # Step the engine over the *same* weather with no player action.
    for rec in window:
        _step(orch, rec)
    engine_end = _root_zone_mineral_n(orch)
    engine_delta = engine_end - anchor_n

    # Sanity: post-#357 the engine genuinely accumulates root-zone mineral N
    # here (net mineralisation dominates the tiny early-season uptake).
    assert engine_delta > 0.0, f"engine did not rise: {engine_delta:.2f}"

    # The fix: the forecast now trends the *same* direction (up), not opposite.
    assert forecast_delta > 0.0, f"forecast did not rise: {forecast_delta:.2f}"

    # Explicit sign agreement (the acceptance criterion).
    assert (forecast_delta > 0) == (engine_delta > 0)

    # Defensible tolerance: the forecast is a conservative but correctly-signed
    # estimate. It should not *overshoot* the engine's rise (the engine's larger
    # increase includes rhizosphere priming, aggregate protection, and root-zone
    # deepening — none of which the heuristic models), and its per-day net
    # mineralisation should sit in a realistic band
    # (~0-3 kg N/ha/day; Stanford & Smith 1972).
    assert 0.0 < forecast_delta < engine_delta
    assert forecast_delta / _HORIZON_DAYS < 3.0


def test_sink_only_projection_would_trend_wrong_way() -> None:
    """Regression guard: without the SOM source term the projection falls.

    This reproduces the #353 bug (sink-only) on the identical anchor state and
    confirms the net-mineralisation source term is what flips the sign from
    down to up. Same-scenario before/after, so the source term is shown to be
    load-bearing rather than incidental.
    """
    orch, records = _build(_ESTABLISH_DAYS + _HORIZON_DAYS)
    for rec in records[:_ESTABLISH_DAYS]:
        _step(orch, rec)

    inputs = _forecast_inputs(orch)
    anchor_n = inputs["mineral_n_kg_ha"]
    window = records[_ESTABLISH_DAYS : _ESTABLISH_DAYS + _HORIZON_DAYS]
    weather = [
        ((r.tmin_c + r.tmax_c) / 2.0, r.shortwave_mj_m2 or 12.0, r.precip_mm or 0.0)
        for r in window
    ]

    with_source = project_soil_forecast(weather=weather, **inputs)

    sink_only_inputs = dict(inputs)
    sink_only_inputs["som_labile_n_kg_ha"] = 0.0
    sink_only = project_soil_forecast(weather=weather, **sink_only_inputs)

    assert sink_only[-1].mineral_n_kg_ha - anchor_n < 0.0  # the old wrong sign
    assert with_source[-1].mineral_n_kg_ha - anchor_n > 0.0  # corrected sign


def _deepening_kwargs(orch: FullSimulationOrchestrator) -> dict[str, object]:
    """Root-growth inputs threaded into the deepening path (#366)."""
    layers = orch.profile.layers
    return {
        "n_no3_by_layer": list(orch.n_state.no3),
        "n_nh4_by_layer": list(orch.n_state.nh4),
        "layer_depths_cm": [ly.depth_cm for ly in layers],
        "root_depth_cm": orch.root_state.current_depth_cm,
        "root_growth_rate_cm_per_day": orch.roots.params.growth_rate_cm_per_day,
        "root_max_depth_cm": orch.roots.params.max_depth_cm,
        "root_stage_multiplier": stage_depth_multiplier(orch.phenology.state.stage),
        "root_penetration_factor": root_penetration_factor(orch.agg_state.mwd(0)),
    }


def test_forecast_deepening_delta_tracks_engine_magnitude() -> None:
    """Root-zone deepening (#366) + aggregate-penetration (#383) match engine Δ.

    #366 made the forecast N-trend *rise* with the engine but, by omitting the
    engine's constraint factor, the projected zone deepened ~2× too fast and the
    Δ over-shot the engine by ~2.1×. #383 threads the **aggregate-penetration**
    channel of that constraint (``root_penetration_factor(agg_state.mwd(0))``,
    cf ≈ 0.50 here) into the daily depth increment, throttling the deepening to
    the engine's constrained rate and bringing the Δ *inside ±20%* of the engine.

    Pinned scenario: established maize on ``loam_temperate`` (NL, seed 42),
    20-day establishment, 5-day no-action horizon — the exact anchor the #353
    reference numbers were measured on (anchor ≈ 239.6, engine Δ ≈ +98.5 kg/ha).

    Measured on this scenario:

        ===============================  ======  ======  ======  =====
        series                           anchor    +5 d       Δ  ratio
        ===============================  ======  ======  ======  =====
        engine                            239.6   338.1   +98.5   1.00
        forecast, constant depth            "     242.1    +2.5   0.03
        forecast, deepening cf-omitted      "     447.7  +208.1   2.11
        forecast, deepening + cf (#383)     "     345.0  +105.4   1.07
        ===============================  ======  ======  ======  =====

    Threading cf collapses the ~2.1× overshoot to **ratio ≈ 1.07**, comfortably
    inside the ±20% band [0.80, 1.20]. The residual +7% is source-side and out of
    scope for #383 (rhizosphere priming, aggregate protection — see
    ``project_soil_forecast``); no band escape hatch was needed. Only the
    aggregate-penetration channel is threaded; the engine's depth-triggered
    hardpan/water-table multipliers do not bind on this horizon and are
    intentionally omitted (see ``_advance_root_depth``).
    """
    orch, records = _build(_ESTABLISH_DAYS + _HORIZON_DAYS)
    for rec in records[:_ESTABLISH_DAYS]:
        _step(orch, rec)

    inputs = _forecast_inputs(orch)
    anchor_n = inputs["mineral_n_kg_ha"]
    deep_kwargs = _deepening_kwargs(orch)
    window = records[_ESTABLISH_DAYS : _ESTABLISH_DAYS + _HORIZON_DAYS]
    weather = [
        ((r.tmin_c + r.tmax_c) / 2.0, r.shortwave_mj_m2 or 12.0, r.precip_mm or 0.0)
        for r in window
    ]

    const_depth = project_soil_forecast(weather=weather, **inputs)
    deepening = project_soil_forecast(weather=weather, **inputs, **deep_kwargs)
    const_delta = const_depth[-1].mineral_n_kg_ha - anchor_n
    deep_delta = deepening[-1].mineral_n_kg_ha - anchor_n

    for rec in window:
        _step(orch, rec)
    engine_delta = _root_zone_mineral_n(orch) - anchor_n

    # Sign agreement (#353 property) must survive.
    assert engine_delta > 0.0, f"engine did not rise: {engine_delta:.2f}"
    assert deep_delta > 0.0, f"deepening forecast did not rise: {deep_delta:.2f}"

    # Deepening is load-bearing: it lifts the projection from a near-flat +~2.5
    # (constant depth, mineralisation only) to a clear rise tracking the engine.
    assert deep_delta > const_delta

    # AC2 (#383): with the aggregate-penetration factor threaded, the deepening Δ
    # lands within ±20% of the engine Δ. Measured ratio ≈ 1.07 here (cf ≈ 0.50).
    ratio = deep_delta / engine_delta
    assert 0.8 <= ratio <= 1.2, f"deepening Δ ratio {ratio:.2f} outside ±20% [0.8, 1.2]"


def test_forecast_deepening_leaves_water_channel_unchanged() -> None:
    """#366 must not perturb the water-stress channel (no #318/#353 regression).

    Same anchor + weather, with and without the deepening inputs: every day's
    ``water_stress`` must be byte-identical. Only the mineral-N channel reads the
    root-growth params.
    """
    orch, records = _build(_ESTABLISH_DAYS + _HORIZON_DAYS)
    for rec in records[:_ESTABLISH_DAYS]:
        _step(orch, rec)

    inputs = _forecast_inputs(orch)
    window = records[_ESTABLISH_DAYS : _ESTABLISH_DAYS + _HORIZON_DAYS]
    weather = [
        ((r.tmin_c + r.tmax_c) / 2.0, r.shortwave_mj_m2 or 12.0, r.precip_mm or 0.0)
        for r in window
    ]

    const_depth = project_soil_forecast(weather=weather, **inputs)
    deepening = project_soil_forecast(
        weather=weather, **inputs, **_deepening_kwargs(orch)
    )

    assert [p.water_stress for p in const_depth] == [p.water_stress for p in deepening]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
