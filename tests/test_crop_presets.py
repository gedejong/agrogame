from __future__ import annotations

from pathlib import Path

import pytest

from agrogame.plant.presets import (
    CropPreset,
    load_crop_presets,
    _load_crop_presets_cached,
)


def test_load_crops() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    assert len(lib.crops) == 7
    for name in [
        "maize",
        "winter_wheat",
        "spring_wheat",
        "rice",
        "sorghum",
        "grape",
        "soybean",
    ]:
        assert name in lib.crops


def test_preset_types() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    for crop in lib.crops.values():
        assert isinstance(crop, CropPreset)
        assert crop.phenology.base_temperature_c < crop.phenology.max_temperature_c
        assert crop.canopy.lai_max > 0
        assert crop.roots.max_depth_cm > 0


def test_winter_wheat_has_vernalization() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    ww = lib.crops["winter_wheat"]
    assert ww.phenology.vernalization_required_units is not None
    assert ww.phenology.vernalization_required_units > 0


def test_spring_wheat_no_vernalization() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    sw = lib.crops["spring_wheat"]
    assert sw.phenology.vernalization_required_units is None


def test_spring_wheat_shorter_cycle_than_winter() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    sw = lib.crops["spring_wheat"]
    ww = lib.crops["winter_wheat"]
    assert sw.phenology.thresholds.maturity_gdd < ww.phenology.thresholds.maturity_gdd


def test_grape_lower_rue_than_maize() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    grape = lib.crops["grape"]
    maize = lib.crops["maize"]
    assert (
        grape.canopy.radiation_use_efficiency_g_per_mj
        < maize.canopy.radiation_use_efficiency_g_per_mj
    )


def test_sorghum_heat_tolerant() -> None:
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    sorghum = lib.crops["sorghum"]
    maize = lib.crops["maize"]
    assert sorghum.canopy.temp_max_c > maize.canopy.temp_max_c
    assert sorghum.canopy.temp_opt_c > maize.canopy.temp_opt_c


def test_missing_file_raises() -> None:
    _load_crop_presets_cached.cache_clear()
    with pytest.raises(FileNotFoundError):
        load_crop_presets(Path("nonexistent.yaml"))


def test_caching() -> None:
    _load_crop_presets_cached.cache_clear()
    p = Path("data/crops/presets.yaml")
    a = load_crop_presets(p)
    b = load_crop_presets(p)
    assert a is b


def test_different_phenology_timelines() -> None:
    """Different crops should have different GDD thresholds."""
    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    maturity_gdds = {
        name: crop.phenology.thresholds.maturity_gdd for name, crop in lib.crops.items()
    }
    assert len(set(maturity_gdds.values())) >= 3


def test_orchestrator_accepts_crop_preset() -> None:
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from datetime import date

    _load_crop_presets_cached.cache_clear()
    lib = load_crop_presets(Path("data/crops/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]

    for crop_name in ["maize", "winter_wheat", "spring_wheat", "grape"]:
        crop = lib.crops[crop_name]
        orch = FullSimulationOrchestrator(profile, crop=crop)
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=5.0),
            tmin_c=15.0,
            tmax_c=25.0,
            par_mj_m2=12.0,
            sim_date=date(2024, 6, 1),
        )
        assert orch.canopy.state.biomass_g_m2 >= 0.0
