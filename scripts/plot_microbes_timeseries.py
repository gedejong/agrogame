from __future__ import annotations

import argparse
from pathlib import Path

from agrogame.plots.microbes import plot_microbes_timeseries


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot microbes timeseries")
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    args = parser.parse_args()

    # Ensure out_dir is a directory, not a file path; the suite runner passes files.
    out_dir = args.out_dir
    if out_dir.suffix:
        out_dir = out_dir.parent
    plot_microbes_timeseries(out_dir, args.profile, args.days, pattern=args.pattern)


if __name__ == "__main__":
    main()
