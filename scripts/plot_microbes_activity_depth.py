from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np

from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.microbes.events import MicrobialActivityComputed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Depth-resolved microbial activity heatmap"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/microbes_activity_depth.png"),
        help="Output image",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    orch = FullSimulationOrchestrator(profile)

    n_layers = len(profile.layers)
    # buffer updated during each day by event callback
    activity_layers: List[float] = [0.0] * n_layers

    def _on_activity(ev: MicrobialActivityComputed) -> None:
        if 0 <= ev.layer < n_layers:
            activity_layers[ev.layer] = float(ev.activity_index)

    orch.event_bus.subscribe(MicrobialActivityComputed, _on_activity)

    act_by_day: List[List[float]] = []

    for _day in range(args.days):
        # reset buffer each day (values overwritten by callbacks)
        for i in range(n_layers):
            activity_layers[i] = 0.0
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=10.0,
            tmax_c=22.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )
        act_by_day.append(list(activity_layers))

    A = np.array(act_by_day, dtype=float).T  # shape: layers x days

    fig, ax = plt.subplots(1, 1, figsize=(6, 5), constrained_layout=True)
    im = ax.imshow(A, aspect="auto", origin="lower", cmap="plasma")
    ax.set_title("Microbial activity (index)")
    ax.set_xlabel("Day")
    ax.set_ylabel("Layer (top=0)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
