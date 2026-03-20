from __future__ import annotations

import argparse
from pathlib import Path
from agrogame.plots.et import plot_et_timeseries
from agrogame.weather.cli import add_weather_args


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot ET timeseries (ET0, potential/actual E/T)"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--out", type=Path, default=Path("out/et_timeseries.png"))
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal", "storms"], default="constant"
    )
    parser.add_argument("--smooth-window", type=int, default=1)
    parser.add_argument("--stress-highlight", action="store_true")
    parser.add_argument("--stress-threshold", type=float, default=0.7)
    add_weather_args(parser)
    args = parser.parse_args()

    plot_et_timeseries(
        profile=args.profile,
        days=args.days,
        out=args.out,
        pattern=args.pattern,
        smooth_window=args.smooth_window,
        stress_highlight=args.stress_highlight,
        stress_threshold=args.stress_threshold,
        weather_args=args,
    )


if __name__ == "__main__":
    main()
