from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Tuple
import typing

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
from agrogame.atmosphere.et.ports import (
    WaterProfile as ETWaterProfile,
    WaterState as ETWaterState,
    WaterActuator,
)
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
    parser = argparse.ArgumentParser(
        description="Export Graphviz DOT of event dependencies"
    )
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/events_graph.dot"))
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

    soil_lib = load_soil_presets(Path("data/soils/presets.yaml"))
    base = soil_lib.soils["loam_temperate"]
    profile = base
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    # Keep nitrogen cycle simple for dependency tracing; water/profile not required here
    ncycle = NitrogenCycle(event_bus=bus, state=nstate)
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

    # Simulate and capture same-day causal edges (chronological)
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
        # Cast soil types to ET interfaces for mypy
        _ = etmod.actual_et(
            typing.cast(ETWaterProfile, profile),
            typing.cast(ETWaterState, wstate),
            typing.cast(WaterActuator, water),
            comps,
            root_fracs,
        )
        _ = ncycle.daily_step(temperature_c=0.5 * (tmin + tmax), plant_demand_kg_ha=1.0)

    # Build transitions by walking the recorded event stream in order
    edges: Dict[Tuple[str, str], int] = {}
    if rec.events:
        prev = rec.events[0]
        for cur in rec.events[1:]:
            a = bucket(prev.event_type, prev.module_name)
            b = bucket(cur.event_type, cur.module_name)
            if a != b:
                edges[(a, b)] = edges.get((a, b), 0) + 1
            prev = cur

    # Emit DOT
    lines = [
        "digraph G {",
        "  rankdir=LR;",
        '  node [shape=box, style=filled, fillcolor="#f6f8fa", color="#9aa0a6"];',
    ]
    for name in MODULE_BUCKET.keys():
        lines.append(f'  "{name}";')
    for (a, b), cnt in edges.items():
        lines.append(f'  "{a}" -> "{b}" [label="{cnt}", color="#d62728"];')
    lines.append("}")

    args.out.write_text("\n".join(lines))
    print(f"Wrote DOT: {args.out}")

    # Try rendering with graphviz dot if available
    dot_bin = shutil.which("dot")
    if dot_bin:
        png_out = args.out.with_suffix(".png")
        try:
            subprocess.run(
                [dot_bin, "-Tpng", str(args.out), "-o", str(png_out)], check=True
            )
            print(f"Rendered PNG: {png_out}")
        except subprocess.CalledProcessError as e:
            print(f"dot render failed: {e}")


if __name__ == "__main__":  # pragma: no cover
    main()
