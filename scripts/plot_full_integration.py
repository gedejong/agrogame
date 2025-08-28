from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.events import EventBus
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
    PhenologyStage,
)
from agrogame.soil.nitrogen import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.plant.roots import RootModule, RootParams, RootState


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot integrated modules over time")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/full_integration.png"))
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

    roots = RootModule(RootParams(), event_bus=bus)
    rstate = RootState()

    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)

    # Time series
    runoff: List[float] = []
    deep: List[float] = []
    evap: List[float] = []
    dS: List[float] = []
    lai: List[float] = []
    biomass: List[float] = []
    stage_series: List[PhenologyStage] = []
    root_depth: List[float] = []
    n_no3_top: List[float] = []

    for _ in range(args.days):
        # Weather drivers (simple constants)
        tmin, tmax, par = 10.0, 22.0, 12.0
        rain, evap0 = 3.0, 2.0

        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        stage_series.append(phen.state.stage)

        # Water balance
        fx = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=rain, evaporation_mm=evap0)
        )
        runoff.append(fx.runoff_mm)
        deep.append(fx.deep_drainage_mm)
        evap.append(fx.evap_mm)
        dS.append(fx.storage_change_mm)

        # Canopy and biomass
        _ = canopy.daily_step(
            incident_par_mj_m2=par, temp_factor=1.0, water_stress=1.0, n_stress=1.0
        )
        biomass.append(canopy.state.biomass_g_m2)
        lai.append(canopy.state.lai)

        # Roots
        _ = roots.daily_step(rstate, profile, phen.state.stage)
        root_depth.append(rstate.current_depth_cm)

        # Nitrogen daily step (demand simplistic, root fractions from cached event)
        _ = ncycle.daily_step(temperature_c=18.0, plant_demand_kg_ha=1.0)
        n_no3_top.append(nstate.no3[0])

    x = list(range(1, args.days + 1))
    fig, ax = plt.subplots(3, 2, figsize=(12, 10))

    # Water fluxes
    ax[0, 0].plot(x, runoff, label="runoff")
    ax[0, 0].plot(x, deep, label="deep")
    ax[0, 0].plot(x, evap, label="evap")
    ax[0, 0].plot(x, dS, label="dS")
    ax[0, 0].set_title("Water fluxes")
    ax[0, 0].legend()

    # Canopy
    ax[0, 1].plot(x, lai, label="LAI")
    ax[0, 1].plot(x, biomass, label="Biomass (g/m2)")
    ax[0, 1].set_title("Canopy development")
    ax[0, 1].legend()

    # Phenology stages (as steps)
    ax[1, 0].step(x, [s.value for s in stage_series], where="post")
    ax[1, 0].set_title("Phenology stage index")

    # Roots
    ax[1, 1].plot(x, root_depth, label="root depth (cm)")
    ax[1, 1].set_title("Root depth")
    ax[1, 1].legend()

    # Nitrogen
    ax[2, 0].plot(x, n_no3_top, label="NO3 top layer (kg/ha)")
    ax[2, 0].set_title("Nitrogen NO3 (top layer)")
    ax[2, 0].legend()

    # Empty subplot reserved for future coupling visuals
    ax[2, 1].axis("off")

    fig.tight_layout()
    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
