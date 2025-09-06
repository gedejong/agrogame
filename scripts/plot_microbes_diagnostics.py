from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np

from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.microbes.events import SubstrateAvailable


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostics: WFPS, pH, substrate")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/microbes_diagnostics.png"),
        help="Output image",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    orch = FullSimulationOrchestrator(profile)

    n_layers = len(profile.layers)
    # Track substrate made available to microbes each day by layer
    substrate: List[float] = [0.0] * n_layers

    def _on_sub(ev: SubstrateAvailable) -> None:
        if 0 <= ev.layer < n_layers:
            substrate[ev.layer] = float(ev.available_c_kg_ha)

    orch.event_bus.subscribe(SubstrateAvailable, _on_sub)

    W: List[List[float]] = []  # wfps by layer x day
    P: List[List[float]] = []  # ph by layer x day
    S: List[List[float]] = []  # substrate by layer x day

    for _day in range(args.days):
        # reset substrate buffer; runtime will emit depth-wise values this day
        for i in range(n_layers):
            substrate[i] = 0.0
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=0.0, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=10.0,
            tmax_c=22.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )
        # WFPS from water_state and porosity
        wfps = []
        for i, layer in enumerate(profile.layers):
            theta = orch.water_state.theta[i]
            porosity = max(1e-6, layer.saturation)
            wfps.append(max(0.0, min(1.0, theta / porosity)))
        ph = list(orch.chem.ph_by_layer)

        W.append(wfps)
        P.append(ph)
        S.append(list(substrate))

    W = np.array(W).T
    P = np.array(P).T
    S = np.array(S).T

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), constrained_layout=True)
    im0 = axes[0].imshow(W, aspect="auto", origin="lower", cmap="Blues")
    axes[0].set_title("WFPS")
    axes[0].set_xlabel("Day")
    axes[0].set_ylabel("Layer (top=0)")
    fig.colorbar(im0, ax=axes[0], fraction=0.046, pad=0.04)

    im1 = axes[1].imshow(P, aspect="auto", origin="lower", cmap="viridis")
    axes[1].set_title("pH")
    axes[1].set_xlabel("Day")
    fig.colorbar(im1, ax=axes[1], fraction=0.046, pad=0.04)

    im2 = axes[2].imshow(S, aspect="auto", origin="lower", cmap="magma")
    axes[2].set_title("Substrate available (C kg/ha)")
    axes[2].set_xlabel("Day")
    fig.colorbar(im2, ax=axes[2], fraction=0.046, pad=0.04)

    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
