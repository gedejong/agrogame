from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator


def _seasonal_series(
    days: int, base: float, amplitude: float, period: int
) -> List[float]:
    import math

    return [
        base + amplitude * math.sin(2 * math.pi * (i / max(1, period)))
        for i in range(days)
    ]


def _storm_series(
    days: int, base: float, storm_every: int, storm_amount: float
) -> List[float]:
    vals: List[float] = []
    for i in range(days):
        vals.append(base + (storm_amount if (i % max(1, storm_every) == 0) else 0.0))
    return vals


def simulate_phosphorus(
    profile_name: str,
    days: int,
    rainfall_mm: float,
    evaporation_mm: float,
    pattern: str = "constant",
) -> Tuple[List[float], List[float], List[float]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]

    orch = FullSimulationOrchestrator(profile)

    total_org: List[float] = []
    total_avail: List[float] = []
    total_fixed: List[float] = []

    if pattern == "seasonal":
        rains = _seasonal_series(
            days, rainfall_mm, amplitude=rainfall_mm * 0.8, period=30
        )
        evaps = _seasonal_series(
            days, evaporation_mm, amplitude=evaporation_mm * 0.5, period=30
        )
    elif pattern == "storms":
        rains = _storm_series(
            days, base=rainfall_mm * 0.2, storm_every=7, storm_amount=rainfall_mm * 3.0
        )
        evaps = [evaporation_mm] * days
    else:
        rains = [rainfall_mm] * days
        evaps = [evaporation_mm] * days

    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rains[i], irrigation_mm=0.0, evaporation_mm=evaps[i]
            ),
            tmin_c=15.0,
            tmax_c=25.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )

        total_org.append(sum(orch.p_state.organic_p))
        total_avail.append(sum(orch.p_state.available_p))
        total_fixed.append(sum(orch.p_state.fixed_p))

    return total_org, total_avail, total_fixed


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot phosphorus pools timeseries")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--rain", type=float, default=5.0)
    parser.add_argument("--evap", type=float, default=2.0)
    parser.add_argument(
        "--out", type=Path, default=Path("out/phosphorus_timeseries.png")
    )
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    total_org, total_avail, total_fixed = simulate_phosphorus(
        profile_name=args.profile,
        days=args.days,
        rainfall_mm=args.rain,
        evaporation_mm=args.evap,
        pattern=args.pattern,
    )

    x = list(range(1, args.days + 1))
    plt.figure(figsize=(10, 6))
    plt.plot(x, total_org, label="organic P (kg/ha)")
    plt.plot(x, total_avail, label="available P (kg/ha)")
    plt.plot(x, total_fixed, label="fixed P (kg/ha)")
    plt.xlabel("Day")
    plt.ylabel("P mass (kg/ha)")
    plt.title(f"Phosphorus pools – {args.profile} ({args.pattern})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
