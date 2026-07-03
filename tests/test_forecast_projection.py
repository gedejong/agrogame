"""Unit tests for the decision-support forecast projection (#318)."""

from __future__ import annotations

from itertools import pairwise

import pytest

from agrogame.api.forecast import (
    SoilForecastPoint,
    _som_moisture_factor,
    _som_temperature_factor,
    project_soil_forecast,
    root_zone_mineral_n_kg_ha,
    root_zone_som_labile_n_kg_ha,
    root_zone_water_mm,
    root_zone_wfps,
    water_stress_coefficient,
)
from agrogame.soil.som.pools import ThreePoolSOM


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
    # (5+3) g/m² mineral N in the rooted layer only -> 80 kg/ha.
    n = root_zone_mineral_n_kg_ha([5.0, 9.0], [3.0, 0.0], [30.0, 30.0], 30.0)
    assert n == pytest.approx(80.0)  # (5+3) g/m² in layer 1 only, ×10


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
    )
    assert pts[-1].mineral_n_kg_ha < 90.0
    assert all(p.mineral_n_kg_ha >= 0.0 for p in pts)


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


def test_root_zone_som_labile_n_partial_last_layer() -> None:
    # Two 30 cm layers, roots reach 45 cm -> full first + half second; SOM
    # pools are already kg/ha so there is no g/m² conversion.
    n = root_zone_som_labile_n_kg_ha([40.0, 20.0], [30.0, 30.0], root_depth_cm=45.0)
    assert n == pytest.approx(40.0 + 0.5 * 20.0)  # 50.0


def test_root_zone_som_labile_n_zero_below_roots() -> None:
    n = root_zone_som_labile_n_kg_ha([40.0, 99.0], [30.0, 30.0], root_depth_cm=30.0)
    assert n == pytest.approx(40.0)


def test_root_zone_som_labile_n_missing_pool_is_zero() -> None:
    # No SOM pool supplied (e.g. som module absent) -> no source, no IndexError.
    assert root_zone_som_labile_n_kg_ha([], [30.0, 30.0], root_depth_cm=45.0) == 0.0


def test_root_zone_wfps_weights_rooted_layers() -> None:
    # Roots reach 45 cm: layer 1 full (frac 1), layer 2 half (frac 0.5).
    # theta/sat = 0.2/0.4 = 0.5 and 0.3/0.5 = 0.6; weighted mean by fraction.
    w = root_zone_wfps([0.2, 0.3], [0.4, 0.5], [30.0, 30.0], root_depth_cm=45.0)
    assert w == pytest.approx((0.5 * 1.0 + 0.6 * 0.5) / 1.5)


def test_root_zone_wfps_falls_back_when_no_saturation() -> None:
    # Zero saturation everywhere -> neutral default (decomposition optimum).
    w = root_zone_wfps([0.2, 0.2], [0.0, 0.0], [30.0, 30.0], root_depth_cm=45.0)
    assert w == pytest.approx(0.6)


def test_som_factors_mirror_engine() -> None:
    # The forecast must scale mineralisation with T and moisture exactly like
    # ThreePoolSOM, or forecast and engine would drift apart in magnitude.
    for t in (5.0, 15.0, 25.0, 30.0):
        assert _som_temperature_factor(t) == pytest.approx(
            ThreePoolSOM._temperature_factor(t)
        )
    for wfps in (0.0, 0.3, 0.6, 0.9, 1.0):
        assert _som_moisture_factor(wfps) == pytest.approx(
            ThreePoolSOM._moisture_factor(wfps)
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
        som_labile_n_kg_ha=60.0,
        root_zone_wfps_frac=0.6,
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
        "root_zone_wfps_frac": 0.6,
    }
    with_source = project_soil_forecast(som_labile_n_kg_ha=80.0, **kwargs)
    sink_only = project_soil_forecast(som_labile_n_kg_ha=0.0, **kwargs)
    assert with_source[-1].mineral_n_kg_ha > 90.0
    assert sink_only[-1].mineral_n_kg_ha < 90.0


def test_mineralization_scales_with_temperature() -> None:
    # Q10=2: warmer weather mineralises more, so warm N > cold N at the horizon.
    base = {
        "available_water_mm": 110.0,
        "total_available_water_mm": 120.0,
        "mineral_n_kg_ha": 100.0,
        "lai": 0.0,
        "som_labile_n_kg_ha": 80.0,
        "root_zone_wfps_frac": 0.6,
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
        som_labile_n_kg_ha=40.0,
        root_zone_wfps_frac=0.6,
    )
    assert pts[-1].mineral_n_kg_ha < 100.0
    assert all(p.mineral_n_kg_ha >= 0.0 for p in pts)


def test_dry_soil_suppresses_mineralization() -> None:
    # Near-zero WFPS -> moisture factor ~0 -> negligible mineralisation, so with
    # no uptake (LAI 0) N barely changes.
    pts = project_soil_forecast(
        available_water_mm=100.0,
        total_available_water_mm=120.0,
        mineral_n_kg_ha=100.0,
        lai=0.0,
        weather=[(20.0, 12.0, 0.0)] * 5,
        som_labile_n_kg_ha=60.0,
        root_zone_wfps_frac=0.0,
    )
    assert pts[-1].mineral_n_kg_ha == pytest.approx(100.0)
