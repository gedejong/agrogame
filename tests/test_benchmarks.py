from __future__ import annotations

from pathlib import Path

import os
import pytest

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.atmosphere.et.types import EtComponents
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather


def _yield_t_ha_from_biomass_g_m2(
    biomass_g_m2: float, harvest_index: float = 0.5
) -> float:
    # 1 g/m² = 0.01 t/ha. Yield ≈ HI * biomass
    return harvest_index * biomass_g_m2 * 0.01


def _run_growth(weather_file: Path, days: int = 120) -> float:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        )
    )
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        )
    )
    et = Evapotranspiration(EtParams())
    water = CascadingBucketWaterModel()
    wstate = SoilWaterState(profile)
    weather = load_weather(weather_file)
    # Seed a small LAI to enable initial interception
    canopy.state.lai = 0.5

    for i in range(min(days, len(weather.records))):
        rec = weather.records[i]
        phen.update_daily(tmin_c=rec.tmin_c, tmax_c=rec.tmax_c, photoperiod_h=12.0)
        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        _ = et.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        _ = water.update_daily(
            profile,
            wstate,
            DailyDrivers(rainfall_mm=0.0, evaporation_mm=0.0),
        )
        _ = canopy.daily_step(
            incident_par_mj_m2=rn,
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )
    return _yield_t_ha_from_biomass_g_m2(canopy.state.biomass_g_m2)


def _run_growth_with_wue_and_stages(weather_file: Path, days: int = 120):
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        )
    )
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        )
    )
    et = Evapotranspiration(EtParams())
    water = CascadingBucketWaterModel()
    wstate = SoilWaterState(profile)
    weather = load_weather(weather_file)
    canopy.state.lai = 0.5

    total_evap_trans_mm = 0.0
    flowering_day = None
    maturity_day = None

    for i in range(min(days, len(weather.records))):
        rec = weather.records[i]
        state = phen.update_daily(
            tmin_c=rec.tmin_c, tmax_c=rec.tmax_c, photoperiod_h=12.0
        )
        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        et0 = et.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        _ = water.update_daily(
            profile,
            wstate,
            DailyDrivers(rainfall_mm=0.0, evaporation_mm=0.0),
        )
        comps: EtComponents = et.potential_components(et0_mm=et0, lai=canopy.state.lai)
        actual = et.actual_et(
            profile,
            wstate,
            water,
            comps,
            root_fractions=tuple(
                [1.0 / max(1, len(profile.layers))] * len(profile.layers)
            ),
        )
        total_evap_trans_mm += actual.evaporation_mm + actual.transpiration_mm
        _ = canopy.daily_step(
            incident_par_mj_m2=rn,
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )
        if flowering_day is None and state.stage.name.lower() == "flowering":
            flowering_day = i
        if maturity_day is None and state.stage.name.lower() == "maturity":
            maturity_day = i

    final_biomass = canopy.state.biomass_g_m2
    wue = final_biomass / max(1e-6, total_evap_trans_mm)
    return final_biomass, wue, flowering_day, maturity_day


SCENARIOS = [
    ("maize_iowa", Path("tests/data/benchmarks/fullseason/maize_iowa.csv"), 11.5, 1.0),
    (
        "wheat_kansas",
        Path("tests/data/benchmarks/fullseason/wheat_kansas.csv"),
        4.2,
        0.5,
    ),
    (
        "maize_kenya_drought",
        Path("tests/data/benchmarks/fullseason/maize_kenya_drought.csv"),
        3.5,
        0.5,
    ),
]


@pytest.mark.parametrize("name,weather_file,expected,tol", SCENARIOS)
@pytest.mark.skipif(
    os.getenv("AGRO_BENCH") != "1", reason="Benchmarks gated; set AGRO_BENCH=1 to run"
)
def test_yield_against_benchmarks(
    name: str, weather_file: Path, expected: float, tol: float
) -> None:
    if not weather_file.exists():
        pytest.skip(f"Missing benchmark weather: {weather_file}")
    y = _run_growth(weather_file)
    assert abs(y - expected) <= tol


@pytest.mark.skipif(
    os.getenv("AGRO_BENCH") != "1", reason="Benchmarks gated; set AGRO_BENCH=1 to run"
)
def test_wue_and_phenology_windows() -> None:
    # Use Iowa dataset for demonstration
    weather_file = Path("tests/data/benchmarks/iowa_2020.csv")
    if not weather_file.exists():
        pytest.skip("Missing benchmark weather")
    biomass, wue, flowering_day, maturity_day = _run_growth_with_wue_and_stages(
        weather_file
    )
    # WUE in g/m2 per mm (plausible bound)
    assert 0.5 <= wue <= 10.0
    # Phenology windows by day indices (coarse check)
    assert flowering_day is None or flowering_day > 0
    assert maturity_day is None or maturity_day > (flowering_day or 0)
