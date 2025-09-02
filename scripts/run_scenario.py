from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.weather import load_weather


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a simple weather-driven scenario")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--weather-file", type=Path, required=True)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("out/summary.csv"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    bus = EventBus()
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        ),
        event_bus=bus,
    )
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )
    et = Evapotranspiration(EtParams())

    weather = load_weather(args.weather_file)

    rows: List[list[str | float]] = [["day", "et0", "act_evap", "act_transp", "lai"]]
    for i in range(min(args.days, len(weather.records))):
        rec = weather.records[i]
        phen.update_daily(tmin_c=rec.tmin_c, tmax_c=rec.tmax_c, photoperiod_h=12.0)
        rain = rec.precip_mm or 0.0
        _ = water.update_daily(
            profile,
            wstate,
            DailyDrivers(rainfall_mm=rain, evaporation_mm=0.0),
        )
        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
        et0 = et.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        comps = et.potential_components(et0_mm=et0, lai=canopy.state.lai)
        n_layers = len(profile.layers)
        root_fracs = tuple([1.0 / n_layers] * n_layers)
        actual = et.actual_et(profile, wstate, water, comps, root_fracs)
        rows.append(
            [
                rec.day.isoformat(),
                et0,
                actual.evaporation_mm,
                actual.transpiration_mm,
                canopy.state.lai,
            ]
        )
        _ = canopy.daily_step_with_transpiration(
            incident_par_mj_m2=par,
            temp_factor=1.0,
            actual_transpiration_mm=actual.transpiration_mm,
            potential_transpiration_mm=comps.potential_transp_mm,
            n_stress=1.0,
        )

    with args.out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
