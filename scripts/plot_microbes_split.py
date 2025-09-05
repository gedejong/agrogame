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
        description="Depth heatmaps: bacterial vs fungal C"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--out", type=Path, default=Path("out/microbes_split.png"), help="Output image"
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    orch = FullSimulationOrchestrator(profile)

    bact_by_day: List[List[float]] = []
    fungi_by_day: List[List[float]] = []

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
        bact_by_day.append(
            [
                ls.c_kg_ha * (1.0 - ls.fungal_fraction)
                for ls in orch.microbes.state.layers
            ]
        )
        fungi_by_day.append(
            [ls.c_kg_ha * ls.fungal_fraction for ls in orch.microbes.state.layers]
        )

    B = np.array(bact_by_day).T  # layers x days
    F = np.array(fungi_by_day).T

    fig, (ax_b, ax_f) = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
    imb = ax_b.imshow(B, aspect="auto", origin="lower", cmap="YlGnBu")
    ax_b.set_title("Bacterial C (kg/ha)")
    ax_b.set_xlabel("Day")
    ax_b.set_ylabel("Layer (top=0)")
    fig.colorbar(imb, ax=ax_b, fraction=0.046, pad=0.04)

    imf = ax_f.imshow(F, aspect="auto", origin="lower", cmap="PuRd")
    ax_f.set_title("Fungal C (kg/ha)")
    ax_f.set_xlabel("Day")
    ax_f.set_ylabel("Layer (top=0)")
    fig.colorbar(imf, ax=ax_f, fraction=0.046, pad=0.04)

    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
