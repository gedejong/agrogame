from __future__ import annotations

from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.sim.builder import build_full_from_preset, generate_rain_evap
from agrogame.soil.water.types import DailyDrivers


def plot_water_timeseries(
    profile: str,
    days: int,
    rain: float,
    evap: float,
    out: Path,
    *,
    pattern: str = "constant",
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    orch = build_full_from_preset(profile)

    storage: List[float] = []
    runoff: List[float] = []
    drainage: List[float] = []
    evap_series: List[float] = []
    transp_series: List[float] = []

    rains, evaps = generate_rain_evap(days, rain, evap, pattern)
    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=15.0,
            tmax_c=25.0,
            par_mj_m2=12.0,
        )
        total = sum(
            orch.water_state.layer_storage_mm(orch.profile, j)
            for j in range(len(orch.profile.layers))
        )
        storage.append(total)
        # Approximate fluxes using deltas and ET events are not directly exposed here;
        # for now, accumulate storage change and use zeros for components.
        runoff.append(0.0)
        drainage.append(0.0)
        evap_series.append(0.0)
        transp_series.append(0.0)

    x = list(range(1, days + 1))
    fig, ax = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    ax[0].plot(x, storage, label="Soil water storage (mm)")
    ax[0].set_ylabel("mm")
    ax[0].legend(loc="upper right")

    ax[1].plot(x, runoff, label="Runoff (mm)")
    ax[1].plot(x, drainage, label="Deep drainage (mm)")
    ax[1].set_ylabel("mm/day")
    ax[1].legend(loc="upper right")

    ax[2].plot(x, evap_series, label="Evaporation (mm)")
    ax[2].plot(x, transp_series, label="Transpiration (mm)")
    ax[2].set_ylabel("mm/day")
    ax[2].set_xlabel("Day")
    ax[2].legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print("Saved", out)
