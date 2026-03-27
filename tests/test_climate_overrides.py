"""Tests for per-climate crop preset overrides (AGRO-102)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agrogame.plant.presets import (
    _apply_canopy_overrides,
    _apply_phenology_overrides,
    _load_crop_presets_cached,
    load_crop_presets,
)


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    _load_crop_presets_cached.cache_clear()


class TestGetPreset:
    def test_base_preset_without_climate(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base = lib.get_preset("maize")
        assert base.canopy.radiation_use_efficiency_g_per_mj == pytest.approx(
            3.56, abs=0.01
        )

    def test_override_applied_for_kenya(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        kenya = lib.get_preset("maize", "kenya_highlands")
        base = lib.get_preset("maize")
        assert (
            kenya.canopy.radiation_use_efficiency_g_per_mj
            < base.canopy.radiation_use_efficiency_g_per_mj
        )

    def test_override_applied_for_sahel(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        sahel = lib.get_preset("maize", "sahel_arid")
        assert sahel.canopy.temp_opt_c == pytest.approx(33.9, abs=0.1)

    def test_fallback_to_base_for_unknown_climate(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base = lib.get_preset("maize")
        unknown = lib.get_preset("maize", "mars_dusty")
        assert unknown == base

    def test_crop_without_overrides_returns_base(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        wheat = lib.get_preset("spring_wheat")
        wheat_nl = lib.get_preset("spring_wheat", "netherlands_temperate")
        assert wheat == wheat_nl


class TestApplyCanopyOverrides:
    def test_rue_overridden(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base_canopy = lib.crops["maize"].canopy
        overridden = _apply_canopy_overrides(base_canopy, {"rue_g_per_mj": 2.5})
        assert overridden.radiation_use_efficiency_g_per_mj == 2.5
        # Other fields unchanged
        assert overridden.lai_max == base_canopy.lai_max

    def test_empty_overrides_returns_same(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base_canopy = lib.crops["maize"].canopy
        result = _apply_canopy_overrides(base_canopy, {})
        assert result == base_canopy

    def test_temp_opt_overridden(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base_canopy = lib.crops["maize"].canopy
        overridden = _apply_canopy_overrides(base_canopy, {"temp_opt_c": 35.0})
        assert overridden.temp_opt_c == 35.0


class TestApplyPhenologyOverrides:
    def test_flowering_gdd_overridden(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base_phen = lib.crops["maize"].phenology
        overridden = _apply_phenology_overrides(base_phen, {"flowering_gdd": 1000.0})
        assert overridden.thresholds.flowering_gdd == 1000.0
        # Other threshold unchanged
        assert overridden.thresholds.maturity_gdd == base_phen.thresholds.maturity_gdd

    def test_empty_overrides_returns_same(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        base_phen = lib.crops["maize"].phenology
        result = _apply_phenology_overrides(base_phen, {})
        assert result == base_phen


class TestYamlParsing:
    def test_maize_has_climate_overrides(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        assert "maize" in lib.climate_overrides
        assert "kenya_highlands" in lib.climate_overrides["maize"]
        assert "sahel_arid" in lib.climate_overrides["maize"]

    def test_override_preserves_non_overridden_fields(self) -> None:
        lib = load_crop_presets(Path("data/crops/presets.yaml"))
        kenya = lib.get_preset("maize", "kenya_highlands")
        base = lib.get_preset("maize")
        # harvest_index not overridden — should match base
        assert kenya.canopy.harvest_index == base.canopy.harvest_index
        # name preserved
        assert kenya.name == base.name
