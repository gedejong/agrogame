from __future__ import annotations

from pathlib import Path

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
    return harvest_index * biomass_g_m2 * 0.01


def diagnose(weather_file: Path, name: str) -> None:
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
    total_et_mm = 0.0
    flowering_idx = None
    maturity_idx = None
    flowering_gdd = None
    maturity_gdd = None

    for i, rec in enumerate(weather.records):
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
            profile, wstate, DailyDrivers(rainfall_mm=0.0, evaporation_mm=0.0)
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
        total_et_mm += actual.evaporation_mm + actual.transpiration_mm
        _ = canopy.daily_step(
            incident_par_mj_m2=rn,
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )
        if flowering_idx is None and state.stage.name.lower() == "flowering":
            flowering_idx = i
            flowering_gdd = state.accumulated_gdd
        if maturity_idx is None and state.stage.name.lower() == "maturity":
            maturity_idx = i
            maturity_gdd = state.accumulated_gdd

    final_biomass = canopy.state.biomass_g_m2
    y = _yield_t_ha_from_biomass_g_m2(final_biomass)
    wue = final_biomass / max(1e-6, total_et_mm)
    print(f"Scenario: {name}")
    print(f"  Weather: {weather_file}")
    print(f"  Final biomass: {final_biomass:.1f} g/m2 -> Yield~ {y:.2f} t/ha (HI=0.5)")
    print(f"  Total ET: {total_et_mm:.1f} mm, WUE: {wue:.2f} g/m2/mm")
    print(f"  Flowering idx/GDD: {flowering_idx} / {flowering_gdd}")
    print(f"  Maturity idx/GDD: {maturity_idx} / {maturity_gdd}")


def main() -> int:
    scenarios = [
        ("maize_iowa", Path("tests/data/benchmarks/iowa_2020.csv")),
        ("wheat_kansas", Path("tests/data/benchmarks/kansas_2020.csv")),
        ("maize_kenya_drought", Path("tests/data/benchmarks/kenya_drought_2019.csv")),
    ]
    for name, wf in scenarios:
        if wf.exists():
            diagnose(wf, name)
        else:
            print(f"Scenario {name}: missing {wf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
