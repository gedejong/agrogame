from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot microbial biomass C/N timeseries"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/microbes_timeseries.png"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    plt.style.use("ggplot")
    orch = FullSimulationOrchestrator(profile)

    total_c: List[float] = []
    total_n: List[float] = []

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
        total_c.append(
            sum(layer_state.c_kg_ha for layer_state in orch.microbes.state.layers)
        )
        total_n.append(
            sum(layer_state.n_kg_ha for layer_state in orch.microbes.state.layers)
        )

    x = list(range(1, args.days + 1))
    fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
    ax.plot(x, total_c, label="Microbial C (kg/ha)")
    ax.plot(x, total_n, label="Microbial N (kg/ha)")
    ax.set_xlabel("Day")
    ax.set_title("Microbial biomass timeseries")
    ax.legend()
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
