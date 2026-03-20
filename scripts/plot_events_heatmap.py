from __future__ import annotations

import argparse
from pathlib import Path
from agrogame.plots.events import plot_heatmap
from agrogame.weather.cli import add_weather_args


def main() -> None:
    parser = argparse.ArgumentParser(description="Event density heatmap (daily)")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/events_heatmap.png"))
    parser.add_argument(
        "--csv-out", type=Path, help="Optional CSV export of daily counts"
    )
    parser.add_argument("--include", type=str, default="")
    parser.add_argument("--exclude", type=str, default="")
    parser.add_argument("--grep", type=str, default="")
    add_weather_args(parser)
    args = parser.parse_args()

    mat = plot_heatmap(
        days=args.days,
        out=args.out,
        weather_args=args,
        include=args.include,
        exclude=args.exclude,
        grep=args.grep,
    )
    if args.csv_out:
        import csv

        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["module", "day", "count"])
            for i, name in enumerate(
                [
                    "Weather",
                    "Soil",
                    "ET",
                    "Plant",
                    "Microbes",
                    "Nitrogen",
                    "Root",
                    "Canopy",
                    "Phosphorus",
                    "Chemistry",
                ]
            ):
                for day in range(len(mat[0])):
                    w.writerow([name, day + 1, mat[i][day]])
        print(f"Saved {args.csv_out}")
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
