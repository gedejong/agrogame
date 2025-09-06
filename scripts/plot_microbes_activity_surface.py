from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from agrogame.soil.microbes.responses import EnvironmentalResponses


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot microbial activity surface vs temperature and WFPS"
    )
    parser.add_argument("--tmin", type=float, default=0.0)
    parser.add_argument("--tmax", type=float, default=35.0)
    parser.add_argument("--wmin", type=float, default=0.1)
    parser.add_argument("--wmax", type=float, default=1.0)
    parser.add_argument("--nT", type=int, default=60)
    parser.add_argument("--nW", type=int, default=60)
    parser.add_argument(
        "--out", type=Path, default=Path("out/microbes_activity_surface.png")
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    resp = EnvironmentalResponses()
    T = np.linspace(args.tmin, args.tmax, args.nT)
    W = np.linspace(args.wmin, args.wmax, args.nW)
    Z = np.zeros((args.nW, args.nT), dtype=float)

    ph = 6.8
    ph_mod = float(resp.ph_modifier(ph))
    for i, w in enumerate(W):
        moist = float(resp.moisture_modifier(float(w)))
        for j, t in enumerate(T):
            temp = float(resp.temperature_modifier(float(t)))
            Z[i, j] = max(0.0, temp * moist * ph_mod)

    fig, ax = plt.subplots(1, 1, figsize=(7, 5), constrained_layout=True)
    im = ax.imshow(
        Z,
        extent=[T.min(), T.max(), W.min(), W.max()],
        origin="lower",
        aspect="auto",
        cmap="viridis",
    )
    ax.set_xlabel("Temperature (°C)")
    ax.set_ylabel("WFPS (fraction)")
    ax.set_title("Microbial activity index (pH=6.8)")
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
