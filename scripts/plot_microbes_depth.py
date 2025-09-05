from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Depth-resolved microbial biomass heatmaps"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--out", type=Path, default=Path("out/microbes_depth.png"), help="Output image"
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    orch = FullSimulationOrchestrator(profile)

    c_by_day: List[List[float]] = []
    n_by_day: List[List[float]] = []

    for _day in range(args.days):
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=10.0,
            tmax_c=22.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )
        c_by_day.append([ls.c_kg_ha for ls in orch.microbes.state.layers])
        n_by_day.append([ls.n_kg_ha for ls in orch.microbes.state.layers])

    C = np.array(c_by_day).T  # shape: layers x days
    N = np.array(n_by_day).T

    fig, (ax_c, ax_n) = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    imc = ax_c.imshow(C, aspect="auto", origin="lower", cmap="viridis")
    ax_c.set_title("Microbial C (kg/ha)")
    ax_c.set_xlabel("Day")
    ax_c.set_ylabel("Layer (top=0)")
    fig.colorbar(imc, ax=ax_c, fraction=0.046, pad=0.04)

    imn = ax_n.imshow(N, aspect="auto", origin="lower", cmap="magma")
    ax_n.set_title("Microbial N (kg/ha)")
    ax_n.set_xlabel("Day")
    ax_n.set_ylabel("Layer (top=0)")
    fig.colorbar(imn, ax=ax_n, fraction=0.046, pad=0.04)

    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
