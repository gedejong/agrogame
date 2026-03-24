from __future__ import annotations

import argparse
from pathlib import Path
from agrogame.plots.events import plot_timeline
from agrogame.weather.cli import add_weather_args


def main() -> None:
    parser = argparse.ArgumentParser(description="Event timeline swimlanes (daily)")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/events_timeline.png"))
    parser.add_argument("--csv-out", type=Path, help="Optional CSV export of events")
    parser.add_argument("--include", type=str, default="")
    parser.add_argument("--exclude", type=str, default="")
    parser.add_argument("--grep", type=str, default="")
    add_weather_args(parser)
    args = parser.parse_args()

    plot_timeline(
        days=args.days,
        out=args.out,
        weather_args=args,
        include=args.include,
        exclude=args.exclude,
        grep=args.grep,
    )
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
