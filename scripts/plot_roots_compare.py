from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.plant.roots import RootModule, RootParams, RootState


def run(
    profile_name: str, days: int, rate: float, max_depth: float, dist: str
) -> Tuple[List[float], List[float]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    bus = EventBus()
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
    roots = RootModule(
        RootParams(
            growth_rate_cm_per_day=rate, max_depth_cm=max_depth, distribution=dist
        ),
        event_bus=bus,
    )
    state = RootState()
    depths: List[float] = []
    top_frac: List[float] = []
    for _ in range(days):
        phen.update_daily(tmin_c=10.0, tmax_c=20.0, photoperiod_h=12.0)
        _ = roots.daily_step(state, profile, phen.state.stage)
        depths.append(state.current_depth_cm)
        top_frac.append(
            (state.layer_fractions or [0.0])[0] if state.layer_fractions else 0.0
        )
    return depths, top_frac


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare root distributions")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--rate", type=float, default=1.5)
    parser.add_argument("--max_depth", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=Path("out/roots_compare.png"))
    args = parser.parse_args()

    d_exp, f_exp = run(
        args.profile, args.days, args.rate, args.max_depth, "exponential"
    )
    d_uni, f_uni = run(args.profile, args.days, args.rate, args.max_depth, "uniform")

    x = list(range(1, args.days + 1))
    fig, ax = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax[0].plot(x, d_exp, label="depth – exponential")
    ax[0].plot(x, d_uni, label="depth – uniform")
    ax[0].legend()
    ax[0].set_ylabel("Depth (cm)")
    ax[0].set_title("Root depth and top-layer fraction: exponential vs uniform")
    ax[1].plot(x, f_exp, label="top-layer frac – exponential")
    ax[1].plot(x, f_uni, label="top-layer frac – uniform")
    ax[1].set_ylabel("Fraction (0-1)")
    ax[1].set_xlabel("Day")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
