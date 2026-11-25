"""Forecast-vs-engine sign-agreement test for the mineral-N projection (#353).

The decision-support forecast (:mod:`agrogame.api.forecast`) must trend the
same direction as the real engine over a short no-action horizon. Before #353
the projection was sink-only (crop uptake + drainage leaching) and trended
*down* while the engine's root-zone mineral N trended *up* — a wrong-sign
indicator that would cue a player to fertilise exactly when soil N is building.

This test establishes maize on ``loam_temperate`` for ~20 days, then compares a
5-day forecast against 5 real no-action engine steps on the *same* weather. The
core assertion is sign agreement. Since #689 the projection's inputs are the
route's own (``_orch_projection_inputs``): the anchor day's engine fluxes (SOM
net mineralisation scaled by Q10 = 2, plant N uptake) held over the horizon,
NO3 leaching by the engine's mixing-cell rule, and the engine's soil
evaporation in the water bucket. The constant-depth projection holds the anchor
root depth, so it omits the root-zone geometry effect (the rooting depth
deepens into more soil each day) that dominates the engine's rise here.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
from weakref import WeakKeyDictionary

import pytest

from agrogame.api.forecast import (
    project_soil_forecast,
    root_zone_mineral_n_kg_ha,
    stage_depth_multiplier,
)
from agrogame.api.routes import _orch_projection_inputs
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
# The weather each run was built on, so the anchor day's temperature can be read
# back by ``_forecast_inputs`` (#689).
_RECORDS: WeakKeyDictionary[FullSimulationOrchestrator, list] = WeakKeyDictionary()
# The deepening inputs, which ``_deepening_kwargs`` supplies separately (#366).
_DEEPENING_KEYS = frozenset(
    {
        "n_no3_by_layer",
        "n_nh4_by_layer",
        "layer_depths_cm",
        "root_depth_cm",
        "root_growth_rate_cm_per_day",
        "root_max_depth_cm",
        "root_stage_multiplier",
        "root_penetration_factor",
    }
)


def _build(
    days: int, seed: int = 42, *, input_fed_reference: bool = True
) -> tuple[FullSimulationOrchestrator, list]:
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
    if input_fed_reference:
        # Preserve the input-fed SOM prior used by the #353/#383 regression
        # scenario. New games instead condition that prior through a fallow.
        orch.som.params = replace(orch.som.params, initial_fallow_days=0)
        orch.som.initialize_from_profile(profile)
    _RECORDS[orch] = series.records
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


def _forecast_inputs(orch: FullSimulationOrchestrator) -> dict[str, object]:
    """The route's constant-depth projection inputs for this anchor (#689).

    The same extraction as ``GET /forecast`` (``_orch_projection_inputs``), with
    the maize preset's p and the last stepped day's mean air temperature, less
    the deepening inputs that ``_deepening_kwargs`` adds.
    """
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    p = crops.get_preset("maize", "netherlands_temperate").depletion_fraction_p
    anchor = _RECORDS[orch][orch.day_counter - 1]
    inputs = _orch_projection_inputs(orch, p, (anchor.tmin_c + anchor.tmax_c) / 2.0)
    return {k: v for k, v in vars(inputs).items() if k not in _DEEPENING_KEYS}


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
    # here (net mineralisation dominates the tiny early-season uptake). Seed 42
    # (#689, kg/ha): engine +7.30, constant-depth forecast +0.89.
    assert engine_delta > 0.0, f"engine did not rise: {engine_delta:.2f}"

    # The fix: the forecast now trends the *same* direction (up), not opposite.
    assert forecast_delta > 0.0, f"forecast did not rise: {forecast_delta:.2f}"

    # Explicit sign agreement (the acceptance criterion).
    assert (forecast_delta > 0) == (engine_delta > 0)

    # Defensible tolerance: the forecast is a conservative but correctly-signed
    # estimate. It should not *overshoot* the engine's rise (the engine's larger
    # increase is mostly root-zone deepening, which the constant-depth path
    # holds fixed), and its per-day net mineralisation should sit in a
    # realistic band (~0-3 kg N/ha/day; Stanford & Smith 1972).
    assert 0.0 < forecast_delta < engine_delta
    assert forecast_delta / _HORIZON_DAYS < 3.0


def test_sink_only_projection_would_trend_wrong_way() -> None:
    """Regression guard: without the SOM source term the projection falls.

    This reproduces the #353 bug (sink-only) on the identical anchor state and
    confirms the net-mineralisation source term is what flips the sign from
    down to up. Same-scenario before/after, so the source term is shown to be
    load-bearing rather than incidental. Seed 42 (#689): sink-only −1.66 kg/ha,
    with the source +0.89.
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
    sink_only_inputs["som_mineralization_kg_ha_day"] = 0.0
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
    20-day establishment, 5-day no-action horizon, the anchor the #353
    reference numbers were measured on. Measured in kg/ha after #689, which
    removed a ×10 that read the engine's kg/ha pools as g/m² (the #383 table
    showed those inflated values: engine +98.5, ratio 1.07):

        ===============================  ======  ======  ======  =====
        series                           anchor    +5 d       Δ  ratio
        ===============================  ======  ======  ======  =====
        engine                            16.93   24.23   +7.30   1.00
        forecast, constant depth            "     17.82   +0.89   0.12
        forecast, deepening + cf (#383)     "     24.40   +7.47   1.02
        ===============================  ======  ======  ======  =====

    The ratio sits inside the ±20% band [0.80, 1.20]. Only the
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

    # Deepening is load-bearing: it lifts the projection from a near-flat +0.89
    # (constant depth) to a clear rise tracking the engine.
    assert deep_delta > const_delta

    # AC2 (#383): with the aggregate-penetration factor threaded, the deepening Δ
    # lands within ±20% of the engine Δ. Measured ratio 1.02 here (#689).
    ratio = deep_delta / engine_delta
    assert 0.8 <= ratio <= 1.2, f"deepening Δ ratio {ratio:.2f} outside ±20% [0.8, 1.2]"


def test_conditioned_default_forecast_tracks_engine_direction() -> None:
    """The production deepening path retains sign agreement after #435.

    The historical ±20% magnitude guard above is specific to the input-fed
    reference. A fallow-conditioned soil has a different source/sink balance;
    the approximate forecast promises direction, not that relative tolerance.
    """
    orch, records = _build(25, input_fed_reference=False)
    for rec in records[:20]:
        _step(orch, rec)
    inputs = _forecast_inputs(orch)
    weather = [
        ((r.tmin_c + r.tmax_c) / 2, r.shortwave_mj_m2 or 12.0, r.precip_mm or 0.0)
        for r in records[20:]
    ]
    forecast = project_soil_forecast(
        weather=weather, **inputs, **_deepening_kwargs(orch)
    )
    for rec in records[20:]:
        _step(orch, rec)
    anchor = inputs["mineral_n_kg_ha"]
    assert _root_zone_mineral_n(orch) > anchor
    assert forecast[-1].mineral_n_kg_ha > anchor


def test_forecast_deepening_leaves_water_channel_unchanged() -> None:
    """#366 must not perturb the water-stress channel (no #318/#353 regression).

    The water channel reads none of the deepening inputs (#689 kept that).

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
