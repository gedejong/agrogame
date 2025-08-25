from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water import CascadingBucketWaterModel, DailyDrivers, SoilWaterState


def simulate_water(
    profile_name: str,
    days: int,
    rainfall_mm: float,
    evaporation_mm: float,
    irrigation_mm: float = 0.0,
):
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]

    state = SoilWaterState(profile)
    model = CascadingBucketWaterModel()

    runoff: List[float] = []
    deep: List[float] = []
    evap: List[float] = []
    dS: List[float] = []

    for _ in range(days):
        flux = model.update_daily(
            profile,
            state,
            DailyDrivers(
                rainfall_mm=rainfall_mm,
                irrigation_mm=irrigation_mm,
                evaporation_mm=evaporation_mm,
            ),
        )
        runoff.append(flux.runoff_mm)
        deep.append(flux.deep_drainage_mm)
        evap.append(flux.evap_mm)
        dS.append(flux.storage_change_mm)

    return runoff, deep, evap, dS


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot water fluxes timeseries")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--rain", type=float, default=5.0)
    parser.add_argument("--evap", type=float, default=2.0)
    parser.add_argument("--irrig", type=float, default=0.0)
    parser.add_argument("--out", type=Path, default=Path("out/water_timeseries.png"))
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    runoff, deep, evap, dS = simulate_water(
        profile_name=args.profile,
        days=args.days,
        rainfall_mm=args.rain,
        evaporation_mm=args.evap,
        irrigation_mm=args.irrig,
    )

    x = list(range(1, args.days + 1))
    plt.figure(figsize=(10, 6))
    plt.plot(x, runoff, label="runoff (mm)")
    plt.plot(x, deep, label="deep drainage (mm)")
    plt.plot(x, evap, label="evap taken (mm)")
    plt.plot(x, dS, label="Δstorage (mm)")
    plt.xlabel("Day")
    plt.ylabel("Water depth (mm)")
    plt.title(f"Water fluxes over time – {args.profile}")
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
