from __future__ import annotations

from pathlib import Path

import pytest

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.weather import load_weather
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.analysis.stats import r2, nse


def _run_simple_season(days: int = 60) -> tuple[list[float], list[float]]:
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
    weather = load_weather(Path("data/weather/sample.csv"))

    biomass: list[float] = []
    lai: list[float] = []
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
        biomass.append(canopy.state.biomass_g_m2)
        lai.append(canopy.state.lai)
    return biomass, lai


def test_biomass_time_series_quality():
    biomass, lai = _run_simple_season(days=30)
    # Use monotonic expectation proxy: compare to linear ramp
    expected = [
        i * (biomass[-1] / max(1, len(biomass) - 1)) for i in range(len(biomass))
    ]
    # Assert correlation quality
    assert r2(expected, biomass) > 0.9
    assert nse(expected, biomass) > 0.8


@pytest.mark.skip(reason="Benchmark datasets not yet added")
def test_yield_and_phenology_against_benchmark():
    # Placeholder for real scenarios (e.g., maize Iowa)
    ...
