from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.events.recorder import EventRecorder
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator
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

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
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
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=rad,
            target_ph=6.8,
        )

    # Aggregate counts per module (by event type prefix heuristics)
    row_names = [
        "Weather",
        "Soil",
        "ET",
        "Plant",
        "Nitrogen",
        "Root",
        "Canopy",
        "Phosphorus",
        "Chemistry",
    ]
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
        if "phosph" in et or "agrogame.soil.phosphorus" in mn:
            return "Phosphorus"
        if "soilph" in et or "chemistry" in mn or "agrogame.soil.chemistry" in mn:
            return "Chemistry"
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
