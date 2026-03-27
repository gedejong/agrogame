from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import (
    ClimatePreset,
    load_climate_presets,
    _load_climate_presets_cached,
)


@pytest.fixture()
def nl_preset() -> ClimatePreset:
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    return lib.climates["netherlands_temperate"]


def test_normal_scenario_physical_bounds(
    nl_preset: ClimatePreset,
) -> None:
    gen = SyntheticWeatherGenerator(nl_preset, seed=42)
    series = gen.generate(90, date(2024, 3, 1))
    assert len(series.records) == 90
    for r in series.records:
        assert -60.0 <= r.tmin_c <= 60.0
        assert r.tmax_c >= r.tmin_c
        assert r.precip_mm is None or r.precip_mm >= 0.0


def test_drought_less_precip_than_normal(
    nl_preset: ClimatePreset,
) -> None:
    gen = SyntheticWeatherGenerator(nl_preset, seed=42)
    normal = gen.generate(180, date(2024, 1, 1), "normal")
    gen_d = SyntheticWeatherGenerator(nl_preset, seed=42)
    drought = gen_d.generate(180, date(2024, 1, 1), "drought")
    normal_total = sum(r.precip_mm or 0.0 for r in normal.records)
    drought_total = sum(r.precip_mm or 0.0 for r in drought.records)
    assert drought_total < normal_total


def test_hot_scenario_warmer(
    nl_preset: ClimatePreset,
) -> None:
    gen_n = SyntheticWeatherGenerator(nl_preset, seed=42)
    normal = gen_n.generate(90, date(2024, 6, 1), "normal")
    gen_h = SyntheticWeatherGenerator(nl_preset, seed=42)
    hot = gen_h.generate(90, date(2024, 6, 1), "hot")
    avg_normal = sum(r.tmax_c for r in normal.records) / len(normal.records)
    avg_hot = sum(r.tmax_c for r in hot.records) / len(hot.records)
    assert avg_hot > avg_normal


def test_seed_reproducibility(
    nl_preset: ClimatePreset,
) -> None:
    gen1 = SyntheticWeatherGenerator(nl_preset, seed=123)
    gen2 = SyntheticWeatherGenerator(nl_preset, seed=123)
    s1 = gen1.generate(30, date(2024, 1, 1))
    s2 = gen2.generate(30, date(2024, 1, 1))
    for r1, r2 in zip(s1.records, s2.records, strict=False):
        assert r1.tmin_c == r2.tmin_c
        assert r1.tmax_c == r2.tmax_c


def test_all_scenarios_run(
    nl_preset: ClimatePreset,
) -> None:
    for scenario in ["normal", "drought", "wet", "hot", "cold"]:
        gen = SyntheticWeatherGenerator(nl_preset, seed=1)
        series = gen.generate(30, date(2024, 1, 1), scenario)
        assert len(series.records) == 30


def test_unknown_scenario_raises(
    nl_preset: ClimatePreset,
) -> None:
    gen = SyntheticWeatherGenerator(nl_preset, seed=1)
    with pytest.raises(ValueError, match="Unknown scenario"):
        gen.generate(10, date(2024, 1, 1), "apocalypse")


def test_extreme_events_can_be_injected() -> None:
    """Use a preset with high extreme probabilities to ensure injection happens."""
    from agrogame.weather.presets import ClimatePreset

    extreme_preset = ClimatePreset(
        name="test_extreme",
        latitude_deg=52.0,
        longitude_deg=5.0,
        annual_mean_tmin_c=5.0,
        annual_mean_tmax_c=15.0,
        annual_temp_amplitude_c=8.0,
        annual_mean_precip_mm_day=2.0,
        annual_mean_rh_pct=70.0,
        annual_mean_wind_m_s=3.0,
        annual_mean_shortwave_mj_m2=12.0,
        heatwave_probability=0.3,
        frost_probability=0.3,
        heavy_rain_probability=0.3,
        heatwave_intensity_c=10.0,
        frost_intensity_c=-8.0,
        heavy_rain_intensity_mm=50.0,
    )
    gen = SyntheticWeatherGenerator(extreme_preset, seed=42)
    series = gen.generate(100, date(2024, 1, 1))
    temps = [r.tmax_c for r in series.records]
    precips = [r.precip_mm or 0.0 for r in series.records]
    # With 30% probabilities over 100 days, extremes should appear
    assert max(temps) > 20.0 or min(r.tmin_c for r in series.records) < -5.0
    assert max(precips) >= 40.0


def test_sahel_scenario() -> None:
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    sahel = lib.climates["sahel_arid"]
    gen = SyntheticWeatherGenerator(sahel, seed=99)
    series = gen.generate(90, date(2024, 6, 1))
    avg_tmax = sum(r.tmax_c for r in series.records) / len(series.records)
    assert avg_tmax > 30.0  # Sahel should be hot


@pytest.mark.parametrize(
    "climate_name",
    ["netherlands_temperate", "kenya_highlands", "sahel_arid"],
)
def test_annual_rainfall_within_10pct_of_expected(climate_name: str) -> None:
    """After normalization, base precip should match annual_mean * 365.

    AC: generate 365 days, verify total precip is close to expected.
    Uses a preset with no extreme events to isolate the normalization
    effect (heavy rain injection adds extra precipitation).
    """
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    source = lib.climates[climate_name]
    # Create a copy without extreme events to test normalization in isolation
    no_extremes = ClimatePreset(
        name=source.name,
        latitude_deg=source.latitude_deg,
        longitude_deg=source.longitude_deg,
        annual_mean_tmin_c=source.annual_mean_tmin_c,
        annual_mean_tmax_c=source.annual_mean_tmax_c,
        annual_temp_amplitude_c=source.annual_temp_amplitude_c,
        annual_mean_precip_mm_day=source.annual_mean_precip_mm_day,
        annual_mean_rh_pct=source.annual_mean_rh_pct,
        annual_mean_wind_m_s=source.annual_mean_wind_m_s,
        annual_mean_shortwave_mj_m2=source.annual_mean_shortwave_mj_m2,
        rainfall_monthly_weights=source.rainfall_monthly_weights,
        heatwave_probability=0.0,
        frost_probability=0.0,
        heavy_rain_probability=0.0,
    )
    expected_annual = source.annual_mean_precip_mm_day * 365.0

    totals: list[float] = []
    for seed in range(10):
        gen = SyntheticWeatherGenerator(no_extremes, seed=seed)
        series = gen.generate(365, date(2024, 1, 1))
        total = sum(r.precip_mm or 0.0 for r in series.records)
        totals.append(total)

    mean_total = sum(totals) / len(totals)
    assert abs(mean_total - expected_annual) / expected_annual < 0.10, (
        f"{climate_name}: mean annual {mean_total:.0f} mm vs "
        f"expected {expected_annual:.0f} mm"
    )
