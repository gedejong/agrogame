from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def run_cmd(args: list[str]) -> None:
    proc = subprocess.run([sys.executable, *args], check=True)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate microbes visualization suite"
    )
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out-dir", type=Path, default=Path("out"))
    parser.add_argument(
        "--skip-depth",
        action="store_true",
        help="Skip bacteria/fungi and enzyme depth heatmaps",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # Timeseries of microbial C and N
    run_cmd(
        [
            "scripts/plot_microbes_timeseries.py",
            "--profile",
            args.profile,
            "--days",
            str(args.days),
            "--out",
            str(args.out_dir / "microbes_timeseries.png"),
        ]
    )

    if not args.skip_depth:
        # Depth heatmaps: total C/N
        run_cmd(
            [
                "scripts/plot_microbes_depth.py",
                "--profile",
                args.profile,
                "--days",
                str(args.days),
                "--out",
                str(args.out_dir / "microbes_depth.png"),
            ]
        )
        # Depth heatmaps: bacteria vs fungi
        run_cmd(
            [
                "scripts/plot_microbes_split.py",
                "--profile",
                args.profile,
                "--days",
                str(args.days),
                "--out",
                str(args.out_dir / "microbes_split.png"),
            ]
        )
        # Depth heatmap: enzyme cost
        run_cmd(
            [
                "scripts/plot_microbes_enzyme_depth.py",
                "--profile",
                args.profile,
                "--days",
                str(args.days),
                "--out",
                str(args.out_dir / "microbes_enzyme_depth.png"),
            ]
        )
        # Depth heatmap: microbial activity
        run_cmd(
            [
                "scripts/plot_microbes_activity_depth.py",
                "--profile",
                args.profile,
                "--days",
                str(args.days),
                "--out",
                str(args.out_dir / "microbes_activity_depth.png"),
            ]
        )
        # Diagnostics: WFPS, pH, substrate
        run_cmd(
            [
                "scripts/plot_microbes_diagnostics.py",
                "--profile",
                args.profile,
                "--days",
                str(args.days),
                "--out",
                str(args.out_dir / "microbes_diagnostics.png"),
            ]
        )

    print("Microbes visualization suite generated in", args.out_dir)


if __name__ == "__main__":
    main()
