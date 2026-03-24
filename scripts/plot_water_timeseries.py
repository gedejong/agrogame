from __future__ import annotations

import argparse
from pathlib import Path

from agrogame.plots.water import plot_water_timeseries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot basic water flux/storage timeseries"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--rain", type=float, default=5.0)
    parser.add_argument("--evap", type=float, default=2.0)
    parser.add_argument("--out", type=Path, default=Path("out/water_timeseries.png"))
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    args = parser.parse_args()

    plot_water_timeseries(
        profile=args.profile,
        days=args.days,
        rain=args.rain,
        evap=args.evap,
        out=args.out,
        pattern=args.pattern,
    )


if __name__ == "__main__":
    main()
