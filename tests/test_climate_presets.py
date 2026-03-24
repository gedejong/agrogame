from __future__ import annotations

from pathlib import Path

import pytest

from agrogame.weather.presets import load_climate_presets, ClimatePreset


def test_load_three_presets() -> None:
    load_climate_presets.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    assert len(lib.climates) == 3
    assert "netherlands_temperate" in lib.climates
    assert "kenya_highlands" in lib.climates
    assert "sahel_arid" in lib.climates


def test_preset_fields_populated() -> None:
    load_climate_presets.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    nl = lib.climates["netherlands_temperate"]
    assert isinstance(nl, ClimatePreset)
    assert nl.latitude_deg == 52.0
    assert nl.annual_mean_tmin_c < nl.annual_mean_tmax_c
    assert 0.0 <= nl.heatwave_probability <= 1.0


def test_sahel_hotter_than_netherlands() -> None:
    load_climate_presets.cache_clear()
    lib = load_climate_presets(Path("data/climate/presets.yaml"))
    nl = lib.climates["netherlands_temperate"]
    sahel = lib.climates["sahel_arid"]
    assert sahel.annual_mean_tmax_c > nl.annual_mean_tmax_c


def test_missing_file_raises() -> None:
    load_climate_presets.cache_clear()
    with pytest.raises(FileNotFoundError):
        load_climate_presets(Path("nonexistent.yaml"))


def test_caching_returns_same_object() -> None:
    load_climate_presets.cache_clear()
    p = Path("data/climate/presets.yaml")
    a = load_climate_presets(p)
    b = load_climate_presets(p)
    assert a is b
