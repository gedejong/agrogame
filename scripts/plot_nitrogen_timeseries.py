from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.nitrogen import NitrogenCycle, SoilNitrogenState
from agrogame.soil.water import DailyDrivers, SoilWaterState
from agrogame.events import EventBus


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


def simulate_nitrogen(
    profile_name: str,
    days: int,
    rainfall_mm: float,
    evaporation_mm: float,
    pattern: str = "constant",
) -> Tuple[List[float], List[float], List[float]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]

    water_state = SoilWaterState(profile)
    n_state = SoilNitrogenState(profile)
    bus = EventBus()
    n_cycle = NitrogenCycle(bus, n_state, water_state=water_state, profile=profile)

    total_org: List[float] = []
    total_nh4: List[float] = []
    total_no3: List[float] = []

    # Minimal water progression to enable leaching events
    from agrogame.soil.water.models.cascading import CascadingBucketWaterModel

    w_model = CascadingBucketWaterModel(event_bus=bus)

    if pattern == "seasonal":
        rains = _seasonal_series(
            days, rainfall_mm, amplitude=rainfall_mm * 0.8, period=30
        )
        evaps = _seasonal_series(
            days, evaporation_mm, amplitude=evaporation_mm * 0.5, period=30
        )
    elif pattern == "storms":
        rains = _storm_series(
            days,
            base=rainfall_mm * 0.2,
            storm_every=7,
            storm_amount=rainfall_mm * 3.0,
        )
        evaps = [evaporation_mm] * days
    else:
        rains = [rainfall_mm] * days
        evaps = [evaporation_mm] * days

    for i in range(days):
        # Advance water to emit movement events
        _ = w_model.update_daily(
            profile,
            water_state,
            DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
        )
        # Advance nitrogen
        _ = n_cycle.daily_step(temperature_c=20.0)

        total_org.append(sum(n_state.organic_n))
        total_nh4.append(sum(n_state.nh4))
        total_no3.append(sum(n_state.no3))

    return total_org, total_nh4, total_no3


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot nitrogen pools timeseries")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--rain", type=float, default=5.0)
    parser.add_argument("--evap", type=float, default=2.0)
    parser.add_argument("--out", type=Path, default=Path("out/nitrogen_timeseries.png"))
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    total_org, total_nh4, total_no3 = simulate_nitrogen(
        profile_name=args.profile,
        days=args.days,
        rainfall_mm=args.rain,
        evaporation_mm=args.evap,
        pattern=args.pattern,
    )

    x = list(range(1, args.days + 1))
    plt.figure(figsize=(10, 6))
    plt.plot(x, total_org, label="organic N (kg/ha)")
    plt.plot(x, total_nh4, label="NH4 (kg/ha)")
    plt.plot(x, total_no3, label="NO3 (kg/ha)")
    plt.xlabel("Day")
    plt.ylabel("N mass (kg/ha)")
    plt.title(f"Nitrogen pools – {args.profile} ({args.pattern})")
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
