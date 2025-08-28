from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams


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
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    bus = EventBus()
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)

    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        ),
        event_bus=bus,
    )
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )

    etmod = Evapotranspiration(EtParams())

    et0s: List[float] = []
    pot_e: List[float] = []
    pot_t: List[float] = []
    act_e: List[float] = []
    act_t: List[float] = []
    lais: List[float] = []

    # Cumulative trackers
    cum_et0 = 0.0
    cum_act_e = 0.0
    cum_act_t = 0.0

    import math

    for day in range(args.days):
        # Synthetic drivers by pattern
        if args.pattern == "seasonal":
            # 30-day cycle
            rad = 10.0 + 6.0 * math.sin(2 * math.pi * (day / 30.0))
            tavg = 16.0 + 6.0 * math.sin(2 * math.pi * (day / 30.0) + math.pi / 6.0)
            tmin, tmax = tavg - 5.0, tavg + 5.0
            # light seasonal rain
            rain = max(
                0.0, 2.0 + 2.0 * math.sin(2 * math.pi * (day / 30.0) + math.pi / 3.0)
            )
            evap0 = 2.0
        elif args.pattern == "storms":
            rad = 12.0
            tmin, tmax = 10.0, 24.0
            # base 0.5 mm plus 8 mm storm every 7 days
            rain = 0.5 + (8.0 if (day % 7 == 0) else 0.0)
            evap0 = 2.0
        else:
            # constant
            tmin, tmax = 10.0, 24.0
            rad = 12.0
            rain, evap0 = 3.0, 2.0
        temp_mean = 0.5 * (tmin + tmax)

        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=rain, evaporation_mm=evap0)
        )

        et0 = etmod.priestley_taylor(temp_mean_c=temp_mean, net_radiation_mj_m2=rad)
        comps = etmod.potential_components(et0_mm=et0, lai=canopy.state.lai)

        # Actuals: use uniform root fractions across layers for demo
        n_layers = len(profile.layers)
        root_fracs = tuple([1.0 / n_layers] * n_layers)
        actual = etmod.actual_et(profile, wstate, water, comps, root_fracs)

        # Update canopy with a simple water stress proxy
        supply = max(1e-9, actual.transpiration_mm)
        demand = max(1e-9, comps.potential_transp_mm)
        water_stress = min(1.0, supply / demand) if demand > 0 else 1.0
        _ = canopy.daily_step(
            incident_par_mj_m2=rad,
            temp_factor=1.0,
            water_stress=water_stress,
            n_stress=1.0,
        )

        et0s.append(et0)
        pot_e.append(comps.potential_evap_mm)
        pot_t.append(comps.potential_transp_mm)
        act_e.append(actual.evaporation_mm)
        act_t.append(actual.transpiration_mm)
        lais.append(canopy.state.lai)
        cum_et0 += et0
        cum_act_e += actual.evaporation_mm
        cum_act_t += actual.transpiration_mm

    x = list(range(1, args.days + 1))
    fig, ax = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
    ax[0].plot(x, et0s, label="ET0 (mm)")
    ax[0].set_title("ET0 and Partitioning")
    ax[0].legend()
    ax[1].plot(x, pot_e, label="Potential Evap (mm)")
    ax[1].plot(x, pot_t, label="Potential Transp (mm)")
    ax[1].plot(x, act_e, label="Actual Evap (mm)")
    ax[1].plot(x, act_t, label="Actual Transp (mm)")
    ax[1].set_ylabel("mm/day")
    # Secondary axis for cumulative ET
    ax1b = ax[1].twinx()
    ax1b.plot(
        x, [sum(et0s[:i]) for i in range(1, len(et0s) + 1)], "k--", label="Cum ET0"
    )
    ax1b.plot(
        x, [sum(act_e[:i]) for i in range(1, len(act_e) + 1)], "C3--", label="Cum Evap"
    )
    ax1b.plot(
        x,
        [sum(act_t[:i]) for i in range(1, len(act_t) + 1)],
        "C4--",
        label="Cum Transp",
    )
    ax1b.set_ylabel("mm (cumulative)")
    # Combine legends
    lines1, labels1 = ax[1].get_legend_handles_labels()
    lines2, labels2 = ax1b.get_legend_handles_labels()
    ax[1].legend(lines1 + lines2, labels1 + labels2, ncol=2)
    ax[2].plot(x, lais, label="LAI")
    ax[2].set_ylabel("LAI")
    ax[2].set_xlabel("Day")
    ax[2].legend()
    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
