"""Unit tests for the decision-support forecast projection (#318)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from agrogame.api.forecast import (
    SoilForecastPoint,
    _advance_root_depth,
    _Bucket,
    _newly_rooted_mineral_n_kg_ha,
    _som_temperature_factor,
    project_soil_forecast,
    root_zone_mineral_n_kg_ha,
    root_zone_sum,
    root_zone_water_mm,
    stage_depth_multiplier,
    _water_day,
    _WaterDrivers,
    water_stress_coefficient,
)
from agrogame.atmosphere.et.module import Evapotranspiration
from agrogame.atmosphere.et.types import EtState
from agrogame.params.phenology import PhenologyStage
from agrogame.plant.roots.module import RootModule
from agrogame.plant.roots.params import RootParams
from agrogame.soil.som.pools import ThreePoolSOM
from agrogame.soil.water.scs import scs_runoff_mm
from agrogame.weather.constants import NET_RAD_FRACTION


def test_root_zone_water_partial_last_layer() -> None:
    # Two 30 cm layers, roots reach 45 cm -> full first layer + half second.
    theta = [0.30, 0.30]
    depths = [30.0, 30.0]
    fc = [0.35, 0.35]
    wp = [0.10, 0.10]
    available, taw = root_zone_water_mm(theta, depths, fc, wp, root_depth_cm=45.0)
    # Layer1: (0.30-0.10)*30*10 = 60 mm; Layer2 half: (0.20)*30*10*0.5 = 30 mm
    assert available == pytest.approx(90.0)
    # TAW layer1: (0.35-0.10)*300 = 75; layer2 half: 0.25*300*0.5 = 37.5
    assert taw == pytest.approx(112.5)


def test_root_zone_water_zero_below_roots() -> None:
    theta = [0.30, 0.30]
    depths = [30.0, 30.0]
    fc = [0.35, 0.35]
    wp = [0.10, 0.10]
    available, taw = root_zone_water_mm(theta, depths, fc, wp, root_depth_cm=30.0)
    assert available == pytest.approx(60.0)
    assert taw == pytest.approx(75.0)


def test_root_zone_mineral_n_converts_to_kg_ha() -> None:
    # The engine's pools are kg/ha (#689): (5+3) kg/ha in the rooted layer only.
    n = root_zone_mineral_n_kg_ha([5.0, 9.0], [3.0, 0.0], [30.0, 30.0], 30.0)
    assert n == pytest.approx(8.0)  # (5+3) kg/ha in layer 1 only, no ×10


def test_water_stress_full_when_wet() -> None:
    # Available above readily-available fraction -> no stress (Ks = 1).
    assert water_stress_coefficient(100.0, 100.0) == 1.0


def test_water_stress_declines_when_depleted() -> None:
    # RAW = 0.5*TAW = 40; available 20 < 40 -> Ks = 20/40 = 0.5.
    ks = water_stress_coefficient(20.0, 80.0)
    assert ks == 0.5


def test_water_stress_zero_when_empty() -> None:
    assert water_stress_coefficient(0.0, 80.0) == 0.0


def test_water_stress_no_capacity_is_neutral() -> None:
    assert water_stress_coefficient(0.0, 0.0) == 1.0


def test_water_stress_full_depletion_fraction_edge() -> None:
    # p = 1.0 -> readily-available = 0; Ks is binary on whether any water exists.
    assert water_stress_coefficient(5.0, 80.0, depletion_fraction_p=1.0) == 1.0
    assert water_stress_coefficient(0.0, 80.0, depletion_fraction_p=1.0) == 0.0


def test_projection_zero_capacity_soil_still_projects() -> None:
    # TAW = 0 exercises the no-holding-capacity branch (rain drains straight
    # through, driving leaching) without dividing by zero.
    pts = project_soil_forecast(
        available_water_mm=0.0,
        total_available_water_mm=0.0,
        mineral_n_kg_ha=100.0,
        lai=0.0,
        weather=[(15.0, 10.0, 60.0)] * 3,
    )
    assert len(pts) == 3
    assert all(p.water_stress == 1.0 for p in pts)  # neutral when no TAW info
    assert pts[-1].mineral_n_kg_ha < 100.0  # drainage leaches N


def test_projection_length_matches_weather() -> None:
    weather = [(15.0, 12.0, 0.0)] * 5
    pts = project_soil_forecast(
        available_water_mm=100.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=3.0,
        weather=weather,
    )
    assert len(pts) == 5
    assert all(isinstance(p, SoilForecastPoint) for p in pts)


def test_projection_dry_spell_increases_water_stress() -> None:
    # Hot, sunny, no rain: water-stress should worsen (Ks decreases).
    weather = [(28.0, 25.0, 0.0)] * 7
    pts = project_soil_forecast(
        available_water_mm=40.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=80.0,
        lai=4.0,
        weather=weather,
    )
    assert pts[-1].water_stress < pts[0].water_stress


def test_projection_mineral_n_depletes_with_uptake() -> None:
    # A growing canopy with no fertiliser draws mineral N down over time.
    weather = [(20.0, 15.0, 0.0)] * 6
    pts = project_soil_forecast(
        available_water_mm=110.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=90.0,
        lai=4.0,
        weather=weather,
        plant_n_uptake_kg_ha_day=2.0,
    )
    assert pts[-1].mineral_n_kg_ha < 90.0
    assert all(p.mineral_n_kg_ha >= 0.0 for p in pts)


def test_projection_mature_crop_applies_no_uptake_sink() -> None:
    # #539 AC10: a crop at MATURITY takes up no N, so with no rain (no leaching)
    # and no SOM source the projection holds the anchor; with uptake on it falls.

    def project(crop_n_uptake: bool) -> list[SoilForecastPoint]:
        return project_soil_forecast(
            available_water_mm=110.0,
            total_available_water_mm=120.0,
            mineral_n_kg_ha=56.4,
            lai=1.1,
            weather=[(20.0, 15.0, 0.0)] * 6,
            som_mineralization_kg_ha_day=0.0,
            plant_n_uptake_kg_ha_day=1.0,
            crop_n_uptake=crop_n_uptake,
        )

    mature = project(crop_n_uptake=False)
    assert [p.mineral_n_kg_ha for p in mature] == [56.4] * 6
    growing = project(crop_n_uptake=True)
    assert all(
        b < a for a, b in pairwise([56.4] + [p.mineral_n_kg_ha for p in growing])
    )
    # Water is not gated at maturity: the stress trajectory is unchanged.
    assert [p.water_stress for p in mature] == [p.water_stress for p in growing]


def test_projection_heavy_rain_leaches_nitrogen() -> None:
    # Compare N loss with vs without large drainage-driving rain.
    dry = project_soil_forecast(
        available_water_mm=120.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=0.0,
        weather=[(15.0, 10.0, 0.0)] * 5,
    )
    wet = project_soil_forecast(
        available_water_mm=120.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=0.0,
        weather=[(15.0, 10.0, 80.0)] * 5,
    )
    # With LAI 0 there is no uptake, so any N loss is leaching only.
    assert wet[-1].mineral_n_kg_ha < dry[-1].mineral_n_kg_ha


def test_projection_empty_weather_returns_empty() -> None:
    pts = project_soil_forecast(
        available_water_mm=100.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=3.0,
        weather=[],
    )
    assert pts == []


# --- Net-mineralisation source term (#353) ---------------------------------


def test_root_zone_mineralization_rate_partial_last_layer() -> None:
    # The engine's per-layer SOM mineralisation (kg/ha/day) weighted by the
    # root zone (#689): roots reach 45 cm -> full first + half second layer.
    n = root_zone_sum([0.4, 0.2], [30.0, 30.0], root_depth_cm=45.0)
    assert n == pytest.approx(0.4 + 0.5 * 0.2)  # 0.5


def test_root_zone_mineralization_rate_zero_below_roots() -> None:
    n = root_zone_sum([0.4, 9.9], [30.0, 30.0], root_depth_cm=30.0)
    assert n == pytest.approx(0.4)


def test_root_zone_mineralization_rate_missing_pool_is_zero() -> None:
    # No SOM flux supplied (e.g. som module absent) -> no source, no IndexError.
    assert root_zone_sum([], [30.0, 30.0], root_depth_cm=45.0) == 0.0


def test_som_factors_mirror_engine() -> None:
    # The forecast must scale mineralisation with T exactly like ThreePoolSOM,
    # or forecast and engine would drift apart in magnitude. The moisture
    # response is in the engine's own rate, which the route reads (#689).
    for t in (5.0, 15.0, 25.0, 30.0):
        assert _som_temperature_factor(t) == pytest.approx(
            ThreePoolSOM._temperature_factor(t)
        )


def test_mineralization_source_increases_n_without_uptake() -> None:
    # Bare soil (LAI 0 -> no uptake) with a labile SOM pool: mineralisation is
    # the only mineral-N flux, so N must accumulate (the #353 fix).
    pts = project_soil_forecast(
        available_water_mm=100.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=0.0,
        weather=[(20.0, 12.0, 0.0)] * 5,
        som_mineralization_kg_ha_day=0.5,
        anchor_temp_c=20.0,
    )
    assert pts[-1].mineral_n_kg_ha > 100.0
    assert all(b.mineral_n_kg_ha >= a.mineral_n_kg_ha for a, b in pairwise(pts))


def test_source_flips_sign_vs_sink_only() -> None:
    # Same anchor + weather: with a labile pool N should rise; without it
    # (sink-only, the old behaviour) N falls. Demonstrates the source term is
    # what corrects the sign.
    kwargs = {
        "available_water_mm": 110.0,
        "total_available_water_mm": 120.0,
        "mineral_n_kg_ha": 90.0,
        "lai": 1.0,
        "weather": [(18.0, 12.0, 0.0)] * 5,
        "anchor_temp_c": 18.0,
        "plant_n_uptake_kg_ha_day": 1.0,
    }
    with_source = project_soil_forecast(som_mineralization_kg_ha_day=2.0, **kwargs)
    sink_only = project_soil_forecast(som_mineralization_kg_ha_day=0.0, **kwargs)
    assert with_source[-1].mineral_n_kg_ha > 90.0
    assert sink_only[-1].mineral_n_kg_ha < 90.0


def test_mineralization_scales_with_temperature() -> None:
    # Q10=2: warmer weather mineralises more, so warm N > cold N at the horizon.
    base = {
        "available_water_mm": 110.0,
        "total_available_water_mm": 120.0,
        "mineral_n_kg_ha": 100.0,
        "lai": 0.0,
        "som_mineralization_kg_ha_day": 1.0,
        "anchor_temp_c": 18.0,
    }
    warm = project_soil_forecast(weather=[(28.0, 12.0, 0.0)] * 5, **base)
    cold = project_soil_forecast(weather=[(8.0, 12.0, 0.0)] * 5, **base)
    assert warm[-1].mineral_n_kg_ha > cold[-1].mineral_n_kg_ha


def test_high_uptake_overrides_source_and_depletes() -> None:
    # A dense canopy draws N faster than the labile pool supplies it, so the
    # projection still falls when uptake dominates (context-appropriate sign).
    pts = project_soil_forecast(
        available_water_mm=110.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=5.0,
        weather=[(20.0, 15.0, 0.0)] * 6,
        som_mineralization_kg_ha_day=0.5,
        anchor_temp_c=20.0,
        plant_n_uptake_kg_ha_day=2.0,
    )
    assert pts[-1].mineral_n_kg_ha < 100.0
    assert all(p.mineral_n_kg_ha >= 0.0 for p in pts)


def test_zero_engine_rate_adds_no_source() -> None:
    # The engine's rate already carries its moisture response (a dry soil
    # mineralises nothing), so a zero rate adds no source on any day (#689).
    pts = project_soil_forecast(
        available_water_mm=100.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=0.0,
        weather=[(30.0, 12.0, 0.0)] * 5,
        som_mineralization_kg_ha_day=0.0,
        anchor_temp_c=10.0,
    )
    assert all(p.mineral_n_kg_ha == pytest.approx(100.0, abs=1e-9) for p in pts)


# --- Root-zone deepening source (#366) -------------------------------------


def test_stage_depth_multiplier_mirrors_engine_defaults() -> None:
    # The forecast duplicates the stage table rather than importing the engine's
    # private method; it must match RootModule._stage_multiplier for every stage.
    engine = RootModule(RootParams())
    for stage in PhenologyStage:
        assert stage_depth_multiplier(stage) == pytest.approx(
            engine._stage_multiplier(stage)
        )
    # Spot-check the documented values.
    assert stage_depth_multiplier(PhenologyStage.VEGETATIVE) == 1.0
    assert stage_depth_multiplier(PhenologyStage.FLOWERING) == 0.6
    assert stage_depth_multiplier(PhenologyStage.GRAIN_FILL) == 0.3
    # The root front stops at maturity, as in the engine (#539).
    assert stage_depth_multiplier(PhenologyStage.MATURITY) == 0.0


def test_stage_depth_multiplier_honours_crop_overrides() -> None:
    # A crop that customises RootParams.stage_multipliers must be mirrored by the
    # forecast too, or the depth projection would silently diverge from the engine
    # (no shipped preset sets one today, but the coupling is now closed). Pass the
    # same override dict both to the engine and to the forecast helper.
    overrides = {
        PhenologyStage.VEGETATIVE: 0.4,  # differs from the 1.0 default
        PhenologyStage.FLOWERING: 0.9,  # differs from the 0.6 default
    }
    engine = RootModule(RootParams(stage_multipliers=overrides))
    for stage in PhenologyStage:
        assert stage_depth_multiplier(stage, overrides) == pytest.approx(
            engine._stage_multiplier(stage)
        )
    # Overridden stages take the crop value; unlisted stages keep the default.
    assert stage_depth_multiplier(PhenologyStage.VEGETATIVE, overrides) == 0.4
    assert stage_depth_multiplier(PhenologyStage.FLOWERING, overrides) == 0.9
    assert stage_depth_multiplier(PhenologyStage.GRAIN_FILL, overrides) == 0.3
    # MATURITY is a hard stop whatever the crop table says (#539).
    assert stage_depth_multiplier(PhenologyStage.MATURITY, overrides) == 0.0
    positive = {PhenologyStage.MATURITY: 0.8}
    assert stage_depth_multiplier(PhenologyStage.MATURITY, positive) == 0.0
    assert RootModule(RootParams(stage_multipliers=positive))._stage_multiplier(
        PhenologyStage.MATURITY
    ) == pytest.approx(0.0)
    # Negative overrides are clamped at 0, matching the engine.
    assert (
        stage_depth_multiplier(
            PhenologyStage.VEGETATIVE, {PhenologyStage.VEGETATIVE: -2.0}
        )
        == 0.0
    )


def test_advance_root_depth_mirrors_engine_and_caps() -> None:
    # depth += growth_rate * stage_mult, capped at max_depth (RootModule).
    assert _advance_root_depth(30.0, 2.0, 120.0) == pytest.approx(32.0)
    # Cap: never exceed max_depth_cm even with a large increment.
    assert _advance_root_depth(119.0, 5.0, 120.0) == pytest.approx(120.0)
    assert _advance_root_depth(120.0, 5.0, 120.0) == pytest.approx(120.0)
    # Negative increment cannot pull roots back up.
    assert _advance_root_depth(30.0, -5.0, 120.0) == pytest.approx(30.0)


def test_newly_rooted_mineral_n_pulls_deeper_layer_n() -> None:
    # Roots 20 -> 30 cm across a 25 cm layer-1 / layer-2 boundary: the increment
    # is the extra rooted fraction of each layer's (anchor-day) mineral N.
    n_no3 = [10.0, 8.0]
    n_nh4 = [0.0, 0.0]
    depths = [25.0, 35.0]
    inc = _newly_rooted_mineral_n_kg_ha(n_no3, n_nh4, depths, 20.0, 30.0)
    # layer1: (25-20)/25 * 10 kg/ha = 2.0; layer2: (30-25)/35 * 8 = 1.142857
    assert inc == pytest.approx(2.0 + 8.0 * 5.0 / 35.0)
    # No deepening -> no increment.
    assert _newly_rooted_mineral_n_kg_ha(n_no3, n_nh4, depths, 30.0, 30.0) == 0.0


def test_deepening_adds_more_n_than_constant_depth() -> None:
    # Same anchor + weather; supplying root-growth params pulls deeper-layer N in
    # as the zone deepens, so the horizon N exceeds the constant-depth path.
    base = {
        "available_water_mm": 100.0,
        "total_available_water_mm": 120.0,
        "mineral_n_kg_ha": root_zone_mineral_n_kg_ha(
            [8.0, 6.0], [4.0, 3.0], [25.0, 35.0], 20.0
        ),
        "lai": 0.0,
        "weather": [(18.0, 12.0, 0.0)] * 5,
        "som_mineralization_kg_ha_day": 0.0,
    }
    const_depth = project_soil_forecast(**base)
    deepening = project_soil_forecast(
        **base,
        n_no3_by_layer=[8.0, 6.0],
        n_nh4_by_layer=[4.0, 3.0],
        layer_depths_cm=[25.0, 35.0],
        root_depth_cm=20.0,
        root_growth_rate_cm_per_day=2.0,
        root_max_depth_cm=120.0,
        root_stage_multiplier=1.0,
    )
    assert deepening[-1].mineral_n_kg_ha > const_depth[-1].mineral_n_kg_ha
    # Water channel is untouched by the deepening inputs.
    assert [p.water_stress for p in deepening] == [p.water_stress for p in const_depth]


def test_deepening_defaults_are_backward_compatible() -> None:
    # Omitting the root-growth params reproduces the constant-depth projection
    # exactly (mirrors #363's zero-default source term).
    kwargs = {
        "available_water_mm": 100.0,
        "total_available_water_mm": 120.0,
        "mineral_n_kg_ha": 90.0,
        "lai": 2.0,
        "weather": [(18.0, 12.0, 0.0)] * 5,
        "som_mineralization_kg_ha_day": 0.6,
        "anchor_temp_c": 18.0,
    }
    baseline = project_soil_forecast(**kwargs)
    # Passing per-layer arrays but zero growth rate must not deepen either.
    zero_growth = project_soil_forecast(
        **kwargs,
        n_no3_by_layer=[8.0, 6.0],
        n_nh4_by_layer=[4.0, 3.0],
        layer_depths_cm=[25.0, 35.0],
        root_depth_cm=20.0,
        root_growth_rate_cm_per_day=0.0,
    )
    assert [p.mineral_n_kg_ha for p in zero_growth] == [
        p.mineral_n_kg_ha for p in baseline
    ]


def test_deepening_respects_depth_cap_no_overshoot() -> None:
    # No mineralisation / uptake / leaching, so the only mineral-N flux is the
    # deepening source — isolating the depth cap.
    common = {
        "available_water_mm": 100.0,
        "total_available_water_mm": 120.0,
        "lai": 0.0,
        "som_mineralization_kg_ha_day": 0.0,
        "n_no3_by_layer": [8.0, 6.0],
        "n_nh4_by_layer": [4.0, 3.0],
        "layer_depths_cm": [25.0, 60.0],
        "root_growth_rate_cm_per_day": 5.0,
        "root_stage_multiplier": 1.0,
        "root_max_depth_cm": 60.0,
    }
    weather = [(18.0, 12.0, 0.0)] * 5

    # Root depth already at the cap: no deepening source at all.
    anchor_at_cap = root_zone_mineral_n_kg_ha(
        [8.0, 6.0], [4.0, 3.0], [25.0, 60.0], 60.0
    )
    at_cap = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor_at_cap, root_depth_cm=60.0, **common
    )
    assert at_cap[-1].mineral_n_kg_ha == pytest.approx(anchor_at_cap)

    # Start at 58 with +5 cm/day and a 60 cm cap: the cap is hit on day 1, so a
    # 5-day horizon reaches the *same* mineral N as a 1-day horizon — no
    # overshoot past the cap on later days.
    anchor_58 = root_zone_mineral_n_kg_ha([8.0, 6.0], [4.0, 3.0], [25.0, 60.0], 58.0)
    capped_5d = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor_58, root_depth_cm=58.0, **common
    )
    capped_1d = project_soil_forecast(
        weather=weather[:1], mineral_n_kg_ha=anchor_58, root_depth_cm=58.0, **common
    )
    assert capped_5d[-1].mineral_n_kg_ha == pytest.approx(capped_1d[-1].mineral_n_kg_ha)
    # And exactly 2 cm of layer 2 was pulled in (58->60), nothing more.
    # Layer 2 mineral N = (no3 6 + nh4 3) kg/ha; 2/60 of it = 0.3 kg/ha.
    assert capped_5d[-1].mineral_n_kg_ha - anchor_58 == pytest.approx(
        (6.0 + 3.0) * 2.0 / 60.0
    )


def test_deepening_increment_scales_with_penetration_factor() -> None:
    # The aggregate-penetration factor (#383) folds into the daily depth
    # increment: cf=1.0 (default) reproduces the pre-#383 deepening, cf=0.5
    # halves the per-day deepening. Isolate the deepening source — lai=0 (no
    # uptake), source=0 (no mineralisation), a single uniform layer (no leaching) —
    # so the only mineral-N flux is the newly-rooted N, which on a uniform layer
    # is linear in the depth increment and therefore halves with cf.
    common = {
        "available_water_mm": 100.0,
        "total_available_water_mm": 120.0,
        "lai": 0.0,
        "som_mineralization_kg_ha_day": 0.0,
        "n_no3_by_layer": [10.0],
        "n_nh4_by_layer": [0.0],
        "layer_depths_cm": [100.0],
        "root_depth_cm": 20.0,
        "root_growth_rate_cm_per_day": 4.0,
        "root_max_depth_cm": 120.0,
        "root_stage_multiplier": 1.0,
    }
    anchor = root_zone_mineral_n_kg_ha([10.0], [0.0], [100.0], 20.0)
    weather = [(18.0, 12.0, 0.0)] * 3  # 3 days, exercise the loop > once

    default = project_soil_forecast(weather=weather, mineral_n_kg_ha=anchor, **common)
    full = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor, root_penetration_factor=1.0, **common
    )
    half = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor, root_penetration_factor=0.5, **common
    )

    # cf defaults to 1.0 -> byte-identical to the explicit cf=1.0 path.
    assert [p.mineral_n_kg_ha for p in default] == [p.mineral_n_kg_ha for p in full]

    d_full = full[-1].mineral_n_kg_ha - anchor
    d_half = half[-1].mineral_n_kg_ha - anchor
    # cf=1.0: 4 cm/day x 3 d = 12 cm into a 100 cm, 10 kg/ha layer -> +1.2 kg/ha.
    assert d_full == pytest.approx(1.2)
    # cf=0.5 halves the daily increment (2 cm/day x 3 d = 6 cm) -> +0.6 kg/ha.
    assert d_half == pytest.approx(0.6)
    assert d_half == pytest.approx(d_full * 0.5)


def test_deepening_penetration_factor_clamped() -> None:
    # cf is clamped to [0, 1]: cf<=0 freezes the depth (no deepening), cf>1 caps
    # at 1.0 (same as the default). Same uniform-layer isolation as above.
    common = {
        "available_water_mm": 100.0,
        "total_available_water_mm": 120.0,
        "lai": 0.0,
        "som_mineralization_kg_ha_day": 0.0,
        "n_no3_by_layer": [10.0],
        "n_nh4_by_layer": [0.0],
        "layer_depths_cm": [100.0],
        "root_depth_cm": 20.0,
        "root_growth_rate_cm_per_day": 4.0,
        "root_max_depth_cm": 120.0,
        "root_stage_multiplier": 1.0,
    }
    anchor = root_zone_mineral_n_kg_ha([10.0], [0.0], [100.0], 20.0)
    weather = [(18.0, 12.0, 0.0)] * 3

    frozen = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor, root_penetration_factor=0.0, **common
    )
    over = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor, root_penetration_factor=5.0, **common
    )
    unit = project_soil_forecast(
        weather=weather, mineral_n_kg_ha=anchor, root_penetration_factor=1.0, **common
    )
    # cf<=0 -> no deepening at all.
    assert frozen[-1].mineral_n_kg_ha == pytest.approx(anchor)
    # cf>1 clamps to 1.0 -> identical to the default deepening.
    assert [p.mineral_n_kg_ha for p in over] == [p.mineral_n_kg_ha for p in unit]


# --- The engine's own fluxes (#689) ----------------------------------------
_ET = Evapotranspiration()


def _drivers(lai: float = 0.0, cn: int | None = None) -> _WaterDrivers:
    """The engine's default ET parameters, no residue, FAO-56 maize p."""
    return _WaterDrivers(
        et=_ET,
        lai=lai,
        curve_number=cn,
        stage1_limit_mm=_ET.params.stage1_limit_mm,
        ritchie_coef=_ET.params.ritchie_coef,
        depletion_fraction_p=0.55,
    )


def _bucket(topsoil: float = 8.0, clock: float = 15.0) -> _Bucket:
    return _Bucket(
        available=40.0,
        taw=60.0,
        topsoil=topsoil,
        topsoil_capacity=20.0,
        topsoil_root_fraction=0.0,
        cumulative_evap_mm=clock,
    )


def _ep(temp_c: float, shortwave: float, lai: float = 0.0) -> float:
    et0 = _ET.priestley_taylor(temp_c, NET_RAD_FRACTION * shortwave)
    return _ET.potential_components(et0, lai).potential_evap_mm


def test_c2_bare_stage2_evaporation_is_the_engines_ritchie() -> None:
    # 15 mm since wetting is past the 6 mm stage-1 limit: stage 2.
    bucket = _bucket()
    drainage, ta_tp = _water_day(bucket, _drivers(), 25.0, 20.0, 0.0)
    clock = EtState(cumulative_evap_mm=15.0)
    expected = _ET.ritchie_evaporation(clock, _ep(25.0, 20.0), 8.0)
    assert 0.0 < expected < _ep(25.0, 20.0)  # stage 2 limits it
    assert 8.0 - bucket.topsoil == pytest.approx(expected, abs=1e-9)
    assert 40.0 - bucket.available == pytest.approx(expected, abs=1e-9)
    assert bucket.cumulative_evap_mm == pytest.approx(clock.cumulative_evap_mm)
    assert (drainage, ta_tp) == (0.0, 1.0)  # bare: no transpiration demand


def test_c2_evaporation_never_exceeds_the_topsoil_water() -> None:
    bucket = _bucket(topsoil=0.4, clock=0.0)  # stage 1, demand far above 0.4 mm
    _water_day(bucket, _drivers(), 30.0, 28.0, 0.0)
    assert bucket.topsoil == pytest.approx(0.0, abs=1e-12)
    assert 40.0 - bucket.available == pytest.approx(0.4)


def test_c2_ten_mm_of_rain_resets_the_stage_clock() -> None:
    # The engine's EtParams.wetting_reset_threshold_mm (10 mm) restarts stage 1.
    wet, dry = _bucket(clock=30.0), _bucket(clock=30.0)
    _water_day(wet, _drivers(), 25.0, 20.0, 10.0)
    _water_day(dry, _drivers(), 25.0, 20.0, 9.9)
    stage1 = min(_ep(25.0, 20.0), wet.topsoil_capacity)
    assert wet.cumulative_evap_mm == pytest.approx(stage1)
    assert dry.cumulative_evap_mm > 30.0


def test_runoff_is_the_engines_scs_curve_number() -> None:
    # 60 mm on CN 86 (loam) runs off 28.75 mm (USDA-SCS NEH-4); no ET at Rs 0.
    bucket = _Bucket(
        available=0.0,
        taw=400.0,
        topsoil=0.0,
        topsoil_capacity=20.0,
        topsoil_root_fraction=0.0,
        cumulative_evap_mm=0.0,
    )
    _water_day(bucket, _drivers(cn=86), 20.0, 0.0, 60.0)
    assert bucket.available == pytest.approx(60.0 - scs_runoff_mm(60.0, 86))
    assert bucket.topsoil == pytest.approx(20.0)  # capped at its FC - WP


def test_c3_transpiration_uses_the_crops_p() -> None:
    # 40 mm of 100: Ks = 40/45 with maize's p 0.55, 40/50 with the generic 0.5.
    common = {
        "available_water_mm": 40.0,
        "total_available_water_mm": 100.0,
        "mineral_n_kg_ha": 10.0,
        "lai": 6.0,
        "weather": [(20.0, 15.0, 0.0)],
    }
    crop = project_soil_forecast(depletion_fraction_p=0.55, **common)[0]
    generic = project_soil_forecast(**common)[0]
    assert crop.water_stress > generic.water_stress
    assert generic.water_stress < 0.8 < crop.water_stress < 40.0 / 45.0


def test_leaching_moves_no3_only() -> None:
    # No ET (Rs 0); a full bucket drains all 80 mm of rain; W_fc is 80 mm.
    def leached(no3_share: float, fc_mm: float) -> float:
        rows = project_soil_forecast(
            available_water_mm=50.0,
            total_available_water_mm=50.0,
            mineral_n_kg_ha=10.0,
            lai=0.0,
            weather=[(15.0, 0.0, 80.0)],
            no3_share=no3_share,
            root_zone_fc_mm=fc_mm,
        )
        return 10.0 - rows[0].mineral_n_kg_ha

    assert leached(0.0, 80.0) == 0.0  # NH4 does not move with the water
    assert leached(1.0, 80.0) == pytest.approx(10.0)  # D = W_fc flushes the NO3
    assert leached(0.4, 160.0) == pytest.approx(10.0 * 0.4 * 0.5)
    assert leached(0.4, 0.0) == pytest.approx(4.0)  # no FC storage: all the NO3


def test_source_is_the_engines_rate_scaled_by_q10() -> None:
    # Rate 0.5 kg/ha/day at 15 °C; a 25 °C day doubles it (Q10 = 2).
    rows = project_soil_forecast(
        available_water_mm=50.0,
        total_available_water_mm=60.0,
        mineral_n_kg_ha=4.0,
        lai=0.0,
        weather=[(25.0, 10.0, 0.0), (15.0, 10.0, 0.0)],
        som_mineralization_kg_ha_day=0.5,
        anchor_temp_c=15.0,
    )
    assert [p.mineral_n_kg_ha for p in rows] == [5.0, 5.5]


def test_uptake_is_the_anchor_rate_unless_the_crop_is_mature() -> None:
    common = {
        "available_water_mm": 50.0,
        "total_available_water_mm": 60.0,
        "mineral_n_kg_ha": 4.0,
        "lai": 2.0,
        "weather": [(20.0, 15.0, 0.0)] * 3,
        "plant_n_uptake_kg_ha_day": 1.5,
    }
    growing = project_soil_forecast(**common)
    mature = project_soil_forecast(crop_n_uptake=False, **common)
    assert [p.mineral_n_kg_ha for p in growing] == [2.5, 1.0, 0.0]  # floored at 0
    assert [p.mineral_n_kg_ha for p in mature] == [4.0] * 3
