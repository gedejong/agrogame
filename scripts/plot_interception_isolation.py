from __future__ import annotations

import argparse
from pathlib import Path

from agrogame.plots.interception import plot_interception_isolation


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot interception isolation")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--rain", type=float, default=3.0)
    parser.add_argument(
        "--out", type=Path, default=Path("out/interception_isolation.png")
    )
    args = parser.parse_args()

    plot_interception_isolation(
        profile=args.profile,
        days=args.days,
        rain=args.rain,
        out=args.out,
    )


if __name__ == "__main__":
    main()
