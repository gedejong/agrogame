from __future__ import annotations

import argparse
import csv
from pathlib import Path

from agrogame.analysis.stats import (
    align_series,
    r2,
    rmse,
    mae,
    mbe,
    nse,
    willmott_d,
    coverage_within,
)


def load_csv(path: Path, key: str, value: str) -> tuple[list, list[float]]:
    xs: list = []
    vs: list[float] = []
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            xs.append(row[key])
            vs.append(float(row[value]))
    return xs, vs


def main() -> int:
    p = argparse.ArgumentParser(
        description="Compare observed vs simulated series (CSV)"
    )
    p.add_argument("--obs", type=Path, required=True)
    p.add_argument("--sim", type=Path, required=True)
    p.add_argument("--key", required=True, help="Key column name (e.g., date)")
    p.add_argument("--obs-col", required=True, help="Observed value column")
    p.add_argument("--sim-col", required=True, help="Simulated value column")
    p.add_argument("--tol", type=float, default=0.5, help="Tolerance for coverage")
    args = p.parse_args()

    ox, ov = load_csv(args.obs, args.key, args.obs_col)
    sx, sv = load_csv(args.sim, args.key, args.sim_col)
    ao, asv = align_series(ox, sx, ov, sv)

    print(f"N={len(ao)}")
    print(f"R2={r2(ao, asv):.3f}")
    print(f"RMSE={rmse(ao, asv):.3f}")
    print(f"MAE={mae(ao, asv):.3f}")
    print(f"MBE={mbe(ao, asv):.3f}")
    print(f"NSE={nse(ao, asv):.3f}")
    print(f"Willmott_d={willmott_d(ao, asv):.3f}")
    print(f"Coverage(|e|<= {args.tol})={coverage_within(ao, asv, args.tol):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
