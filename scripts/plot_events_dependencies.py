from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

from agrogame.events import EventBus
from agrogame.events.recorder import EventRecorder
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series
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


MODULE_BUCKET = {
    "Weather": ["Weather"],
    "Soil": ["Water", "Soil"],
    "ET": ["Evap", "Transpir", "Et"],
    "Plant": ["Plant"],
    "Nitrogen": ["Nitrogen", "NO3", "N_"],
    "Root": ["Root"],
    "Canopy": ["Canopy", "LAI", "Biomass"],
}


def bucket(event_type: str, module_name: str = "") -> str:
    et = event_type.lower()
    mn = module_name.lower()
    for name, keys in MODULE_BUCKET.items():
        for k in keys:
            if k.lower() in et:
                return name
    if "nutrient" in et or "agrogame.soil.nitrogen" in mn:
        return "Nitrogen"
    return "Plant"


def main() -> None:
    parser = argparse.ArgumentParser(description="Event dependency (circular) graph")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--fc-scale",
        type=float,
        default=0.8,
        help="Scale factor to reduce field capacity for all layers (e.g., 0.8)",
    )
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--out", type=Path, default=Path("out/events_dependencies.png"))
    add_weather_args(parser)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    bus = EventBus()
    rec = EventRecorder(bus)

    # Modules
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

    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    base = soil_lib.soils["loam_temperate"]
    # Apply field capacity scaling while preserving bounds
    new_layers = []
    for lyr in base.layers:
        wp, fc, sat = lyr.wilting_point, lyr.field_capacity, lyr.saturation
        nfc = max(wp + 0.005, min(sat - 0.005, fc * args.fc_scale))
        new_layers.append(lyr.model_copy(update={"field_capacity": float(nfc)}))
    profile = base.model_copy(update={"layers": new_layers})
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

    # Simulate and capture simple causal edges: same-day bucket transitions
    for day in range(total):
        rec.set_day(day + 1)
        if series is not None:
            w = series.records[day]
            if weather_module is not None:
                _ = weather_module.emit_for_day(day)
            tmin, tmax, rad = w.tmin_c, w.tmax_c, (w.net_radiation_mj_m2 or 12.0)
            rain = w.precip_mm or 0.0
        else:
            tmin, tmax, rad, rain = 10.0, 22.0, 12.0, 0.0
        # Phenology, canopy
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

    # Build bucket transitions based on chronological order within each day
    edges: Dict[Tuple[str, str], int] = {}
    day_events: Dict[int, list] = {}
    for ev in rec.events:
        day_events.setdefault(ev.day_index or 0, []).append(ev)

    for _, evs in day_events.items():
        modules = [bucket(e.event_type, e.module_name) for e in evs]
        for a, b in zip(modules, modules[1:], strict=False):
            if a == b:
                continue
            edges[(a, b)] = edges.get((a, b), 0) + 1

    # Draw circular dependency graph
    nodes = list(MODULE_BUCKET.keys())
    N = len(nodes)
    import math

    angles = [2 * math.pi * i / N for i in range(N)]
    pos = {nodes[i]: (math.cos(ang), math.sin(ang)) for i, ang in enumerate(angles)}

    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(10, 10), constrained_layout=True)
    # Nodes (bigger, readable labels)
    for name, (x, y) in pos.items():
        ax.plot(x, y, "o", color="#1f77b4", markersize=18, zorder=3)
        txt = ax.text(
            x,
            y,
            name,
            ha="center",
            va="center",
            fontsize=13,
            color="black",
            weight="bold",
            zorder=4,
        )
        txt.set_path_effects([pe.withStroke(linewidth=3, foreground="white")])
    # Edge widths normalized
    max_cnt = max(edges.values()) if edges else 1
    for (a, b), cnt in edges.items():
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        lw = 0.6 + 4.0 * (cnt / max_cnt) ** 0.7
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={
                "arrowstyle": "->",
                "lw": lw,
                "color": "#d62728",
                "alpha": 0.65,
                "shrinkA": 12,
                "shrinkB": 12,
                "connectionstyle": "arc3,rad=0.25",
            },
        )
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Event dependency (bucketed, same-day transitions)")
    ax.set_aspect("equal")
    fig.savefig(args.out, dpi=args.dpi)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
