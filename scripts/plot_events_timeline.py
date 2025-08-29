from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

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
    parser = argparse.ArgumentParser(description="Event timeline swimlanes (daily)")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/events_timeline.png"))
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

    # Soil/water/nitrogen/roots/ET wiring to surface more events
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

    # Simulate to record events
    for day in range(total):
        rec.set_day(day + 1)
        if series is not None:
            w = series.records[day]
            # Emit DailyWeather event for visibility
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

        # Roots update to obtain fractions
        _ = roots.daily_step(rstate, profile, phen.state.stage)
        root_fracs = (
            tuple(rstate.layer_fractions)
            if rstate.layer_fractions is not None
            else tuple([1.0 / len(profile.layers)] * len(profile.layers))
        )

        # Interception + soil water update to trigger water events
        intercepted, throughfall = istate.intercept(canopy.state.lai, rain)
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=throughfall, evaporation_mm=0.0)
        )

        # ET actuals to trigger transpiration extraction events
        et0 = etmod.priestley_taylor(
            temp_mean_c=0.5 * (tmin + tmax), net_radiation_mj_m2=rad
        )
        comps = etmod.potential_components(et0_mm=et0, lai=canopy.state.lai)
        _ = etmod.actual_et(profile, wstate, water, comps, root_fracs)
        # Nitrogen cycle step (subscribed to TranspirationByLayer events for mass-flow)
        _ = ncycle.daily_step(temperature_c=0.5 * (tmin + tmax), plant_demand_kg_ha=1.0)

    # Build swimlanes by module family
    lanes = ["Weather", "Soil", "ET", "Plant", "Nitrogen", "Root", "Canopy"]
    lane_y: Dict[str, int] = {name: i for i, name in enumerate(lanes)}
    colors = {
        "Weather": "#1f77b4",
        "Soil": "#17becf",
        "ET": "#2ca02c",
        "Plant": "#bcbd22",
        "Nitrogen": "#8c564b",
        "Root": "#9467bd",
        "Canopy": "#ff7f0e",
    }

    def bucket(event_type: str) -> str:
        et = event_type.lower()
        if "weather" in et:
            return "Weather"
        if "water" in et or "soil" in et:
            return "Soil"
        if "evap" in et or "transpir" in et:
            return "ET"
        if "nitrogen" in et or "n_" in et or "no3" in et:
            return "Nitrogen"
        if "root" in et:
            return "Root"
        if "canopy" in et or "lai" in et or "biomass" in et:
            return "Canopy"
        return "Plant"

    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    ax.set_yticks(range(len(lanes)))
    ax.set_yticklabels(lanes)
    ax.set_xlabel("Day")
    ax.set_title("Event timeline (daily swimlanes)")

    # Plot as small markers per event
    for ev in rec.events:
        x = ev.day_index or 1
        lane = bucket(ev.event_type)
        y = lane_y[lane]
        ax.plot(x, y, marker="|", color=colors[lane], markersize=8, linestyle="None")

    ax.set_xlim(1, total)
    ax.set_ylim(-0.5, len(lanes) - 0.5)
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
