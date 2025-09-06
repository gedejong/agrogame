from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict

import matplotlib.pyplot as plt

from agrogame.events.recorder import EventRecorder
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.weather.module import WeatherModule
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series


def main() -> None:
    parser = argparse.ArgumentParser(description="Event timeline swimlanes (daily)")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/events_timeline.png"))
    parser.add_argument("--csv-out", type=Path, help="Optional CSV export of events")
    parser.add_argument(
        "--include",
        type=str,
        default="",
        help="Comma list of modules to include (e.g., 'Soil,ET'). Empty = all",
    )
    parser.add_argument(
        "--exclude",
        type=str,
        default="",
        help="Comma list of modules to exclude (applied after include)",
    )
    parser.add_argument(
        "--grep",
        type=str,
        default="",
        help="Substring filter on event_type (case-insensitive)",
    )
    add_weather_args(parser)
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Orchestrator with shared EventBus
    # Use default loam profile for the timeline
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    orch = FullSimulationOrchestrator(profile)
    rec = EventRecorder(orch.event_bus)

    series = get_weather_series(args, args.days)
    if series is not None:
        series = sanitize_weather_series(series)
        total = min(args.days, len(series.records))
    else:
        total = args.days

    weather_module = (
        WeatherModule(series, orch.event_bus) if series is not None else None
    )

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
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=rad,
            target_ph=6.8,
        )

    # Build swimlanes by module family
    lanes = [
        "Weather",
        "Soil",
        "ET",
        "Plant",
        "Microbes",
        "Nitrogen",
        "Root",
        "Canopy",
        "Phosphorus",
        "Chemistry",
    ]
    lane_y: Dict[str, int] = {name: i for i, name in enumerate(lanes)}
    colors = {
        "Weather": "#1f77b4",
        "Soil": "#17becf",
        "ET": "#2ca02c",
        "Plant": "#bcbd22",
        "Microbes": "#7f7f7f",
        "Nitrogen": "#8c564b",
        "Root": "#9467bd",
        "Canopy": "#ff7f0e",
        "Phosphorus": "#e377c2",
        "Chemistry": "#d62728",
    }

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
        if "agrogame.soil.microbes" in mn or "microbial" in et:
            return "Microbes"
        if "phosph" in et or "agrogame.soil.phosphorus" in mn:
            return "Phosphorus"
        if "enzymegrouptotals" in et or "enzymeproduced" in et:
            return "Microbes"
        if "soilph" in et or "chemistry" in mn or "agrogame.soil.chemistry" in mn:
            return "Chemistry"
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

    # Build filters
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

    # Plot as small markers per event
    filtered = [ev for ev in rec.events if allow(ev)]
    for ev in filtered:
        x = ev.day_index or 1
        lane = bucket(ev.event_type, ev.module_name)
        y = lane_y[lane]
        ax.plot(x, y, marker="|", color=colors[lane], markersize=8, linestyle="None")

    ax.set_xlim(1, total)
    ax.set_ylim(-0.5, len(lanes) - 0.5)
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")

    # Optional CSV export
    if args.csv_out:
        import csv
        import json

        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                ["day_index", "event_type", "module_name", "timestamp", "data_json"]
            )
            for ev in filtered:
                ts = ev.data.get("timestamp")
                w.writerow(
                    [
                        ev.day_index,
                        ev.event_type,
                        ev.module_name,
                        ts,
                        json.dumps(ev.data, default=str),
                    ]
                )
        print(f"Saved {args.csv_out}")


if __name__ == "__main__":
    main()
