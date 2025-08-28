from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.plant.roots import RootModule, RootParams, RootState


def simulate_roots(
    profile_name: str,
    days: int,
    growth_rate_cm_per_day: float,
    max_depth_cm: float,
    distribution: str,
) -> tuple[List[float], List[float], List[List[float]]]:
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
            growth_rate_cm_per_day=growth_rate_cm_per_day,
            max_depth_cm=max_depth_cm,
            distribution=distribution,
        ),
        event_bus=bus,
    )
    state = RootState()

    depths: List[float] = []
    top_frac: List[float] = []
    fractions_over_time: List[List[float]] = []

    for _ in range(days):
        phen.update_daily(tmin_c=10.0, tmax_c=20.0, photoperiod_h=12.0)
        _ = roots.daily_step(state, profile, phen.state.stage)
        depths.append(state.current_depth_cm)
        if state.layer_fractions:
            top_frac.append(state.layer_fractions[0])
            fractions_over_time.append(list(state.layer_fractions))
        else:
            top_frac.append(0.0)
            fractions_over_time.append([])

    return depths, top_frac, fractions_over_time


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot root depth and distribution timeseries"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--rate", type=float, default=1.5)
    parser.add_argument("--max_depth", type=float, default=120.0)
    parser.add_argument(
        "--dist", choices=["exponential", "uniform"], default="exponential"
    )
    parser.add_argument("--out", type=Path, default=Path("out/roots_timeseries.png"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    depths, top_frac, fractions_over_time = simulate_roots(
        profile_name=args.profile,
        days=args.days,
        growth_rate_cm_per_day=args.rate,
        max_depth_cm=args.max_depth,
        distribution=args.dist,
    )

    x = list(range(1, args.days + 1))
    fig, ax = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
    ax[0].plot(x, depths, label="root depth (cm)")
    ax[0].set_ylabel("Depth (cm)")
    ax[0].legend()
    ax[0].set_title(f"Root development – {args.profile} ({args.dist})")
    ax[1].plot(x, top_frac, label="top-layer fraction")
    ax[1].set_ylabel("Fraction (0-1)")
    ax[1].set_xlabel("Day")
    ax[1].legend()
    # Stacked fractions view (only first 5 layers for readability)
    if any(frac for frac in fractions_over_time):
        # Determine max number of layers captured
        max_layers = max((len(f) for f in fractions_over_time), default=0)
        show_layers = min(5, max_layers)
        stacked = [
            [(f[i] if i < len(f) else 0.0) for f in fractions_over_time]
            for i in range(show_layers)
        ]
        labels = [f"layer {i}" for i in range(show_layers)]
        ax[2].stackplot(x, *stacked, labels=labels)
        ax[2].set_ylabel("Layer fraction")
        ax[2].set_xlabel("Day")
        ax[2].legend(loc="upper right", ncol=min(5, show_layers))
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
