from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from agrogame.events.recorder import EventRecorder
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Depth heatmap of daily enzyme production cost (kg C/ha·d)"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/microbes_enzyme_depth.png"),
        help="Output image path",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils[args.profile]

    orch = FullSimulationOrchestrator(profile)
    recorder = EventRecorder(orch.event_bus)

    n_layers = len(profile.layers)
    days = int(args.days)
    # layers x days
    enzyme_cost = np.zeros((n_layers, days), dtype=float)

    for day_index in range(days):
        recorder.set_day(day_index + 1)
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=10.0,
            tmax_c=22.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )
        # Sum enzyme production events for this day into the matrix
        # EventRecorder uses 1-based day_index; align with our loop
        for ev in recorder.events:
            if (
                ev.day_index == day_index + 1
                and ev.event_type == "EnzymeProduced"
                and "production_cost_c_kg_ha" in ev.data
                and "layer" in ev.data
            ):
                layer_idx = int(ev.data["layer"]) if ev.data["layer"] is not None else 0
                if 0 <= layer_idx < n_layers:
                    enzyme_cost[layer_idx, day_index] += float(
                        ev.data["production_cost_c_kg_ha"]
                    )

    fig, ax = plt.subplots(figsize=(7.5, 5), constrained_layout=True)
    image = ax.imshow(enzyme_cost, aspect="auto", origin="lower", cmap="cividis")
    ax.set_title("Enzyme cost C (kg/ha·d)")
    ax.set_xlabel("Day")
    ax.set_ylabel("Layer (top=0)")
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
