from __future__ import annotations

import argparse
from pathlib import Path
from agrogame.plots.events import plot_dependencies
from agrogame.weather.cli import add_weather_args


def main() -> None:
    parser = argparse.ArgumentParser(description="Event dependency (circular) graph")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--fc-scale", type=float, default=0.8)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--out", type=Path, default=Path("out/events_dependencies.png"))
    add_weather_args(parser)
    args = parser.parse_args()

    plot_dependencies(
        days=args.days, out=args.out, fc_scale=args.fc_scale, weather_args=args
    )
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
