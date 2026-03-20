from __future__ import annotations

import argparse
from pathlib import Path

from agrogame.plots.microbes import plot_microbes_depth


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot microbes by depth")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    if args.out is not None:
        out_dir = args.out.parent if args.out.suffix else args.out
    plot_microbes_depth(out_dir, args.profile, args.days, pattern=args.pattern)


if __name__ == "__main__":
    main()
