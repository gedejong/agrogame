from __future__ import annotations

import argparse
from pathlib import Path

from agrogame.plots.roots_compare import plot_roots_compare


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare root depth across strategies")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--rate-a", type=float, default=1.5)
    parser.add_argument("--rate-b", type=float, default=2.0)
    parser.add_argument("--max-depth", type=float, default=120.0)
    parser.add_argument("--out", type=Path, default=Path("out/roots_compare.png"))
    args = parser.parse_args()

    plot_roots_compare(
        profile=args.profile,
        days=args.days,
        rate_a=args.rate_a,
        rate_b=args.rate_b,
        max_depth=args.max_depth,
        out=args.out,
    )


if __name__ == "__main__":
    main()
