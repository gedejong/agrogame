from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import (
    ClimatePreset,
    load_climate_presets,
    _load_climate_presets_cached,
)

_PRESETS_YAML = Path(__file__).resolve().parents[1] / "data/climate/presets.yaml"


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


# --- Legacy sinusoid path, pinned (#500 AC2, #560 AC2) -----------------------

# Test-local copies of the three parameter sets in main 6e7919e's
# data/climate/presets.yaml. The shipped presets move onto station normals
# (ADR-019), so these literals are what keeps the legacy sinusoid path guarded.
_LEGACY_PRESETS: dict[str, ClimatePreset] = {
    "netherlands_temperate": ClimatePreset(
        name="Netherlands - Temperate Maritime",
        latitude_deg=52.0,
        longitude_deg=5.5,
        annual_mean_tmin_c=4.0,
        annual_mean_tmax_c=14.0,
        annual_temp_amplitude_c=10.0,
        annual_mean_precip_mm_day=2.3,
        annual_mean_rh_pct=82.0,
        annual_mean_wind_m_s=4.5,
        annual_mean_shortwave_mj_m2=14.0,
        rainfall_monthly_weights=[
            0.9,
            0.7,
            0.8,
            0.8,
            0.9,
            1.0,
            1.1,
            1.0,
            1.1,
            1.3,
            1.2,
            1.0,
        ],
        heatwave_probability=0.005,
        frost_probability=0.02,
        heavy_rain_probability=0.01,
        heatwave_intensity_c=8.0,
        frost_intensity_c=-5.0,
        heavy_rain_intensity_mm=35.0,
    ),
    "kenya_highlands": ClimatePreset(
        name="Kenya Highlands - Tropical Highland",
        latitude_deg=-0.4,
        longitude_deg=36.9,
        annual_mean_tmin_c=10.0,
        annual_mean_tmax_c=24.0,
        annual_temp_amplitude_c=2.0,
        annual_mean_precip_mm_day=3.5,
        annual_mean_rh_pct=65.0,
        annual_mean_wind_m_s=2.0,
        annual_mean_shortwave_mj_m2=18.0,
        rainfall_monthly_weights=[
            0.4,
            0.5,
            1.5,
            2.5,
            2.0,
            0.3,
            0.2,
            0.2,
            0.3,
            1.2,
            1.5,
            1.0,
        ],
        heatwave_probability=0.002,
        frost_probability=0.005,
        heavy_rain_probability=0.02,
        heatwave_intensity_c=6.0,
        frost_intensity_c=-2.0,
        heavy_rain_intensity_mm=50.0,
    ),
    "sahel_arid": ClimatePreset(
        name="Sahel - Semi-Arid",
        latitude_deg=14.0,
        longitude_deg=2.0,
        annual_mean_tmin_c=20.0,
        annual_mean_tmax_c=36.0,
        annual_temp_amplitude_c=6.0,
        annual_mean_precip_mm_day=1.2,
        annual_mean_rh_pct=30.0,
        annual_mean_wind_m_s=3.0,
        annual_mean_shortwave_mj_m2=24.0,
        rainfall_monthly_weights=[
            0.0,
            0.0,
            0.1,
            0.2,
            0.5,
            1.5,
            3.0,
            3.5,
            2.0,
            0.5,
            0.1,
            0.0,
        ],
        heatwave_probability=0.02,
        frost_probability=0.0,
        heavy_rain_probability=0.005,
        heatwave_intensity_c=10.0,
        frost_intensity_c=-3.0,
        heavy_rain_intensity_mm=40.0,
    ),
}

# (preset, record index) -> (tmin_c, tmax_c, shortwave_mj_m2, precip_mm), captured
# on main 3e85226 (generator identical to 6e7919e) before the monthly path
# landed: SyntheticWeatherGenerator(preset, seed=42).generate(400, 2024-03-01).
_LEGACY_GOLDEN: dict[tuple[str, int], tuple[float, float, float, float]] = {
    ("netherlands_temperate", 0): (
        0.5711678887094631,
        10.527947982579077,
        12.459284995217738,
        4.167671291363939,
    ),
    ("netherlands_temperate", 100): (
        15.9003426744077,
        25.07112952889772,
        17.34681039085279,
        1.5787113747388746,
    ),
    ("netherlands_temperate", 399): (
        6.015680421463724,
        14.860172936322552,
        17.369833980071,
        1.7975883403179391,
    ),
    ("kenya_highlands", 0): (
        9.14132518224838,
        23.098105276117995,
        16.0737614011869,
        12.096478471701465,
    ),
    ("kenya_highlands", 100): (
        14.024552140390961,
        27.195338994880984,
        22.528178970955306,
        0.7331422013873561,
    ),
    ("kenya_highlands", 399): (
        10.106298293416124,
        22.950790808274952,
        21.656241299278143,
        8.695698844538382,
    ),
    ("sahel_arid", 0): (
        17.85624653547892,
        33.813026629348535,
        21.495476010140646,
        0.28134165468017436,
    ),
    ("sahel_arid", 100): (
        27.96244740739933,
        43.13323426188935,
        30.30023184110907,
        1.2788645918937336,
    ),
    ("sahel_arid", 399): (
        19.435432902538007,
        41.533469325659546,
        25.91595789694936,
        0.17847428198272766,
    ),
}


@pytest.mark.parametrize("key", sorted(_LEGACY_PRESETS))
def test_legacy_sinusoid_path_is_bit_identical(key: str) -> None:
    """Presets without monthly normals reproduce main's generator to 1e-12.

    Pins the draw order (tmin, tmax, RH, wind, shortwave, precipitation) and
    the legacy arithmetic, so the optional monthly path cannot drift the
    sinusoid presets (#500 AC2).
    """
    records = (
        SyntheticWeatherGenerator(_LEGACY_PRESETS[key], seed=42)
        .generate(400, date(2024, 3, 1))
        .records
    )
    for idx in (0, 100, 399):
        r = records[idx]
        got = (r.tmin_c, r.tmax_c, r.shortwave_mj_m2, r.precip_mm)
        for field_name, value, golden in zip(
            ("tmin_c", "tmax_c", "shortwave_mj_m2", "precip_mm"),
            got,
            _LEGACY_GOLDEN[(key, idx)],
            strict=True,
        ):
            assert value is not None
            assert (
                abs(value - golden) <= 1e-12
            ), f"{key} record {idx} {field_name}: {value!r} != golden {golden!r}"


# --- Station monthly normals: fidelity across years (#560 AC4) -------------


def _shipped_presets_with_normals() -> list[str]:
    _load_climate_presets_cached.cache_clear()
    lib = load_climate_presets(_PRESETS_YAML)
    return sorted(k for k, p in lib.climates.items() if p.monthly_mean_tmin_c)


def test_sahel_ships_on_station_normals() -> None:
    """The Sahel leg (#586) moved ``sahel_arid``; AC4 must never run empty."""
    assert "sahel_arid" in _shipped_presets_with_normals()


@pytest.mark.parametrize("key", _shipped_presets_with_normals())
def test_monthly_normals_fidelity_across_years(key: str) -> None:
    """Every (year, month) mean tracks the station normals over three years.

    Extremes disabled (the heatwave injector biases the means, #579); seeds
    42-46 pooled; 1,096 days from 2024-01-01 cross 29 Feb 2024 and two
    31 Dec -> 1 Jan seams (#531). Tolerances: 0.4 C for tmin and tmax, and
    max(3%, 0.3 MJ/m2) for shortwave, where the max(0, .) clip on the daily
    noise lifts a low-radiation month. Prototype worst: 0.33 C, SW 1.6%.
    """
    _load_climate_presets_cached.cache_clear()
    shipped = load_climate_presets(_PRESETS_YAML).climates[key]
    preset = replace(
        shipped,
        heatwave_probability=0.0,
        frost_probability=0.0,
        heavy_rain_probability=0.0,
    )
    sums: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0] * 4)
    for seed in range(42, 47):
        series = SyntheticWeatherGenerator(preset, seed=seed).generate(
            1096, date(2024, 1, 1)
        )
        for r in series.records:
            acc = sums[(r.day.year, r.day.month)]
            acc[0] += r.tmin_c
            acc[1] += r.tmax_c
            acc[2] += r.shortwave_mj_m2 or 0.0
            acc[3] += 1.0
    assert sorted(sums) == [(y, m) for y in (2024, 2025, 2026) for m in range(1, 13)]
    for (year, month), (tmin, tmax, sw, n) in sorted(sums.items()):
        i = month - 1
        ref_sw = preset.monthly_mean_shortwave_mj_m2[i]
        where = f"{key} {year}-{month:02d}"
        assert abs(tmin / n - preset.monthly_mean_tmin_c[i]) <= 0.4, where
        assert abs(tmax / n - preset.monthly_mean_tmax_c[i]) <= 0.4, where
        assert abs(sw / n - ref_sw) <= max(0.03 * ref_sw, 0.3), where
