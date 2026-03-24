from __future__ import annotations

import argparse
from pathlib import Path
from agrogame.plots.phenology_roots import plot_roots_timeseries


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

    plot_roots_timeseries(
        profile=args.profile,
        days=args.days,
        rate=args.rate,
        max_depth=args.max_depth,
        dist=args.dist,
        out=args.out,
    )


if __name__ == "__main__":
    main()
