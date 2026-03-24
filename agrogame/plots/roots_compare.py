from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.plant.roots import RootModule, RootParams, RootState


def _simulate(
    profile_name: str,
    days: int,
    rate: float,
    max_depth: float,
    dist: str,
) -> List[float]:
    soil = load_soil_presets(Path("soils/presets.yaml")).soils[profile_name]
    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        )
    )
    roots = RootModule(
        RootParams(
            growth_rate_cm_per_day=rate,
            max_depth_cm=max_depth,
            distribution=dist,
        )
    )
    state = RootState()
    depths: List[float] = []
    for _ in range(days):
        phen.update_daily(tmin_c=10.0, tmax_c=20.0, photoperiod_h=12.0)
        _ = roots.daily_step(state, soil, phen.state.stage)
        depths.append(state.current_depth_cm)
    return depths


def plot_roots_compare(
    profile: str,
    days: int,
    rate_a: float,
    rate_b: float,
    max_depth: float,
    out: Path,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    a = _simulate(profile, days, rate_a, max_depth, "exponential")
    b = _simulate(profile, days, rate_b, max_depth, "uniform")

    x = list(range(1, days + 1))
    plt.figure(figsize=(10, 6))
    plt.plot(x, a, label=f"exp rate={rate_a}")
    plt.plot(x, b, label=f"uniform rate={rate_b}")
    plt.xlabel("Day")
    plt.ylabel("Root depth (cm)")
    plt.title("Roots depth compare")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print("Saved", out)
