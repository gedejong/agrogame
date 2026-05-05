from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from agrogame.events.recorder import EventRecorder
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator
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

    # Orchestrator wires all modules on one EventBus
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile)
    rec = EventRecorder(orch.event_bus)

    # Optional external weather series

    series = get_weather_series(args, args.days)
    if series is not None:
        series = sanitize_weather_series(series)
        total = min(args.days, len(series.records))
    else:
        total = args.days
    weather_module = (
        WeatherModule(series, orch.event_bus) if series is not None else None
    )

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
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=rad,
            target_ph=6.8,
        )

    # Build transitions by walking the recorded event stream in order
    edges: dict[tuple[str, str], int] = {}
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
