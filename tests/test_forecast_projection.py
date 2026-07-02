"""Unit tests for the decision-support forecast projection (#318)."""

from __future__ import annotations

import pytest

from agrogame.api.forecast import (
    SoilForecastPoint,
    project_soil_forecast,
    root_zone_mineral_n_kg_ha,
    root_zone_water_mm,
    water_stress_coefficient,
)


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
