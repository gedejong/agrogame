from __future__ import annotations

import argparse
from pathlib import Path
from agrogame.plots.phenology_roots import plot_phenology_canopy


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot phenology and canopy timeseries")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--tmin", type=float, default=10.0)
    parser.add_argument("--tmax", type=float, default=26.0)
    parser.add_argument("--par", type=float, default=12.0, help="MJ m^-2 day^-1")
    parser.add_argument(
        "--pattern", choices=["constant", "seasonal"], default="seasonal"
    )
    parser.add_argument("--out", type=Path, default=Path("out/phenology_canopy.png"))
    parser.add_argument("--show-ribbon", action="store_true")
    parser.add_argument(
        "--efficiency-out", type=Path, default=Path("out/phenology_efficiency.png")
    )
    parser.add_argument(
        "--phase-out", type=Path, default=Path("out/phenology_phase.png")
    )
    args = parser.parse_args()

    plot_phenology_canopy(
        days=args.days,
        tmin=args.tmin,
        tmax=args.tmax,
        par=args.par,
        pattern=args.pattern,
        out=args.out,
        efficiency_out=args.efficiency_out,
        phase_out=args.phase_out,
        show_ribbon=args.show_ribbon,
    )


if __name__ == "__main__":
    main()
