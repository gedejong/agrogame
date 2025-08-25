from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water import CascadingBucketWaterModel, DailyDrivers, SoilWaterState


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


def simulate_water(
    profile_name: str,
    days: int,
    rainfall_mm: float,
    evaporation_mm: float,
    irrigation_mm: float = 0.0,
    pattern: str = "constant",
    plot: str = "fluxes",
) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]

    state = SoilWaterState(profile)
    model = CascadingBucketWaterModel()

    runoff: List[float] = []
    deep: List[float] = []
    evap: List[float] = []
    dS: List[float] = []

    # Build driver series
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

    storage: List[float] = []

    for i in range(days):
        flux = model.update_daily(
            profile,
            state,
            DailyDrivers(
                rainfall_mm=rains[i],
                irrigation_mm=irrigation_mm,
                evaporation_mm=evaps[i],
            ),
        )
        runoff.append(flux.runoff_mm)
        deep.append(flux.deep_drainage_mm)
        evap.append(flux.evap_mm)
        dS.append(flux.storage_change_mm)
        # Track total storage (sum of layer storages)
        total_store = sum(
            state.layer_storage_mm(profile, li) for li in range(len(state.theta))
        )
        storage.append(total_store)

    return runoff, deep, evap, dS, storage


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot water fluxes timeseries")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--rain", type=float, default=5.0)
    parser.add_argument("--evap", type=float, default=2.0)
    parser.add_argument("--irrig", type=float, default=0.0)
    parser.add_argument("--out", type=Path, default=Path("out/water_timeseries.png"))
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    parser.add_argument(
        "--plot", choices=["fluxes", "cumulative", "storage"], default="fluxes"
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    runoff, deep, evap, dS, storage = simulate_water(
        profile_name=args.profile,
        days=args.days,
        rainfall_mm=args.rain,
        evaporation_mm=args.evap,
        irrigation_mm=args.irrig,
        pattern=args.pattern,
        plot=args.plot,
    )

    x = list(range(1, args.days + 1))
    plt.figure(figsize=(10, 6))
    if args.plot == "fluxes":
        plt.plot(x, runoff, label="runoff (mm)")
        plt.plot(x, deep, label="deep drainage (mm)")
        plt.plot(x, evap, label="evap taken (mm)")
        plt.plot(x, dS, label="Δstorage (mm)")
        plt.ylabel("Water depth (mm)")
        plt.title(f"Water fluxes – {args.profile} ({args.pattern})")
    elif args.plot == "cumulative":
        import itertools

        plt.plot(x, list(itertools.accumulate(runoff)), label="cum runoff (mm)")
        plt.plot(x, list(itertools.accumulate(deep)), label="cum deep (mm)")
        plt.plot(x, list(itertools.accumulate(evap)), label="cum evap (mm)")
        plt.ylabel("Cumulative depth (mm)")
        plt.title(f"Cumulative water – {args.profile} ({args.pattern})")
    else:
        plt.plot(x, storage, label="storage (mm)")
        plt.ylabel("Storage (mm)")
        plt.title(f"Storage – {args.profile} ({args.pattern})")
    plt.xlabel("Day")
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
