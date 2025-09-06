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
    parser.add_argument(
        "--fb-adjust", type=float, default=None, help="Override fb_adjust_rate"
    )
    parser.add_argument(
        "--enz-weights",
        type=str,
        default=None,
        help=(
            "Comma-separated weights, e.g."
            " cellulase=0.3,protease=0.3,phosphatase=0.3,urease=0.1"
        ),
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    plt.style.use("ggplot")
    orch = FullSimulationOrchestrator(profile)
    # Apply CLI overrides to microbes params if provided
    if args.fb_adjust is not None:
        orch.microbes.params.fb_adjust_rate = float(args.fb_adjust)
    if args.enz_weights:
        parts = [p.strip() for p in args.enz_weights.split(",") if p.strip()]
        weights: dict[str, float] = {}
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    weights[k.strip()] = float(v)
                except Exception:
                    continue
        if weights:
            orch.microbes.params.enzyme_group_weights = weights

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
