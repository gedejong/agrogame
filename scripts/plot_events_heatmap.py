from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.events import EventBus
from agrogame.events.recorder import EventRecorder
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.plant.roots import RootModule, RootParams, RootState
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.soil.canopy.interception import InterceptionState
from agrogame.weather.module import WeatherModule
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series


def main() -> None:
    parser = argparse.ArgumentParser(description="Event density heatmap (daily)")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/events_heatmap.png"))
    parser.add_argument(
        "--csv-out", type=Path, help="Optional CSV export of daily counts"
    )
    parser.add_argument("--include", type=str, default="")
    parser.add_argument("--exclude", type=str, default="")
    parser.add_argument("--grep", type=str, default="")
    add_weather_args(parser)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    bus = EventBus()
    rec = EventRecorder(bus)

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
    # Wire additional modules to surface more events
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)
    roots = RootModule(RootParams(), event_bus=bus)
    rstate = RootState()
    etmod = Evapotranspiration(EtParams())
    istate = InterceptionState()

    series = get_weather_series(args, args.days)
    if series is not None:
        series = sanitize_weather_series(series)
        total = min(args.days, len(series.records))
    else:
        total = args.days
    weather_module = WeatherModule(series, bus) if series is not None else None

    # Simulate minimal loop to generate events (phenology+canopy)
    for day in range(total):
        rec.set_day(day + 1)
        if series is not None:
            w = series.records[day]
            if weather_module is not None:
                _ = weather_module.emit_for_day(day)
            tmin, tmax, rad = w.tmin_c, w.tmax_c, (w.net_radiation_mj_m2 or 12.0)
            rain = w.precip_mm or 0.0
        else:
            tmin, tmax, rad = 10.0, 22.0, 12.0
            rain = 0.0
        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        _ = canopy.daily_step(
            incident_par_mj_m2=rad, temp_factor=1.0, water_stress=1.0, n_stress=1.0
        )
        _ = roots.daily_step(rstate, profile, phen.state.stage)
        root_fracs = (
            tuple(rstate.layer_fractions)
            if rstate.layer_fractions is not None
            else tuple([1.0 / len(profile.layers)] * len(profile.layers))
        )
        intercepted, throughfall = istate.intercept(canopy.state.lai, rain)
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=throughfall, evaporation_mm=0.0)
        )
        et0 = etmod.priestley_taylor(
            temp_mean_c=0.5 * (tmin + tmax), net_radiation_mj_m2=rad
        )
        comps = etmod.potential_components(et0_mm=et0, lai=canopy.state.lai)
        _ = etmod.actual_et(profile, wstate, water, comps, root_fracs)
        _ = ncycle.daily_step(temperature_c=0.5 * (tmin + tmax), plant_demand_kg_ha=1.0)

    # Aggregate counts per module (by event type prefix heuristics)
    row_names = ["Weather", "Soil", "ET", "Plant", "Nitrogen", "Root", "Canopy"]
    row_index = {n: i for i, n in enumerate(row_names)}
    mat: List[List[int]] = [[0 for _ in range(total)] for _ in range(len(row_names))]

    def bucket(event_type: str, module_name: str = "") -> str:
        et = event_type.lower()
        mn = module_name.lower()
        if "weather" in et:
            return "Weather"
        if "water" in et or "soil" in et:
            return "Soil"
        if "evap" in et or "transpir" in et:
            return "ET"
        if (
            "nitrogen" in et
            or "n_" in et
            or "no3" in et
            or "agrogame.soil.nitrogen" in mn
        ):
            return "Nitrogen"
        if "root" in et:
            return "Root"
        if "canopy" in et or "lai" in et or "biomass" in et:
            return "Canopy"
        return "Plant"

    inc = {s.strip() for s in args.include.split(",") if s.strip()}
    exc = {s.strip() for s in args.exclude.split(",") if s.strip()}
    grep = (args.grep or "").lower()

    def allow(ev) -> bool:
        lane = bucket(ev.event_type, ev.module_name)
        if inc and lane not in inc:
            return False
        if lane in exc:
            return False
        if grep and grep not in ev.event_type.lower():
            return False
        return True

    for ev in rec.events:
        if not allow(ev):
            continue
        r = row_index.get(bucket(ev.event_type, ev.module_name))
        c = (ev.day_index or 1) - 1
        if 0 <= r < len(row_names) and 0 <= c < total:
            mat[r][c] += 1

    # Plot heatmap
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    im = ax.imshow(mat, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(len(row_names)))
    ax.set_yticklabels(row_names)
    ax.set_xlabel("Day")
    ax.set_title("Event density by module (daily)")
    fig.colorbar(im, ax=ax, label="Events/day")
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")

    if args.csv_out:
        import csv

        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["module", "day", "count"])
            for i, name in enumerate(row_names):
                for day in range(total):
                    w.writerow([name, day + 1, mat[i][day]])
        print(f"Saved {args.csv_out}")


if __name__ == "__main__":
    main()
