from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt

from agrogame.events import EventBus
from agrogame.soil.phenology import (
    CropPhenologyParams,
    GrowthStageThresholds,
    PhenologyModule,
    PhenologyStage,
    StageChanged,
)
from agrogame.soil.canopy import CanopyModule, CanopyParams
from agrogame.soil.loader import load_soil_presets
from agrogame.plant.roots import RootModule, RootParams, RootState


def simulate_phenology_canopy(
    days: int, tmin: float, tmax: float, par: float, pattern: str
) -> Tuple[
    List[float],
    List[float],
    List[PhenologyStage],
    List[tuple[int, str]],
    List[float],
    List[float],
]:
    bus = EventBus()
    phen_params = CropPhenologyParams(
        base_temperature_c=8.0,
        max_temperature_c=35.0,
        thresholds=GrowthStageThresholds(
            emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
        ),
    )
    pheno = PhenologyModule(phen_params, event_bus=bus)
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
    stage_marks: List[tuple[int, str]] = []
    lai: List[float] = []
    biomass: List[float] = []
    stages: List[PhenologyStage] = []
    intercepted_series: List[float] = []
    biomass_inc_series: List[float] = []

    def _label(stage: PhenologyStage) -> str:
        mapping = {
            PhenologyStage.PLANTED: "Planted",
            PhenologyStage.EMERGED: "Emergence",
            PhenologyStage.VEGETATIVE: "Vegetative",
            PhenologyStage.FLOWERING: "Flowering",
            PhenologyStage.GRAIN_FILL: "Grain fill",
            PhenologyStage.MATURITY: "Maturity",
        }
        return mapping.get(stage, str(getattr(stage, "name", stage)))

    bus.subscribe(
        StageChanged,
        lambda e: stage_marks.append((len(lai) + 1, _label(e.to_stage))),
    )

    if pattern == "seasonal":
        import math

        tmins = [tmin + 5.0 * math.sin(2 * math.pi * (i / 30.0)) for i in range(days)]
        tmaxs = [tmax + 7.0 * math.sin(2 * math.pi * (i / 30.0)) for i in range(days)]
        pars = [
            par + 0.5 * par * math.sin(2 * math.pi * (i / 30.0)) for i in range(days)
        ]
    else:
        tmins = [tmin] * days
        tmaxs = [tmax] * days
        pars = [par] * days

    for i in range(days):
        state = pheno.update_daily(tmin_c=tmins[i], tmax_c=tmaxs[i], photoperiod_h=12.0)
        stages.append(state.stage)
        fx = canopy.daily_step(
            incident_par_mj_m2=pars[i],
            temp_factor=1.0,
            water_stress=1.0,
            n_stress=1.0,
        )
        intercepted_series.append(fx.intercepted_par_mj_m2)
        biomass_inc_series.append(fx.biomass_increment_g_m2)
        lai.append(canopy.state.lai)
        biomass.append(canopy.state.biomass_g_m2)

    return lai, biomass, stages, stage_marks, intercepted_series, biomass_inc_series


def plot_phenology_canopy(
    days: int,
    tmin: float,
    tmax: float,
    par: float,
    pattern: str,
    out: Path,
    efficiency_out: Path,
    phase_out: Path,
    show_ribbon: bool = False,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lai, biomass, stages, stage_marks, intercepted, biomass_inc = (
        simulate_phenology_canopy(
            days=days, tmin=tmin, tmax=tmax, par=par, pattern=pattern
        )
    )
    x = list(range(1, days + 1))
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(x, lai, label="LAI", color="tab:green")
    ax1.set_xlabel("Day")
    ax1.set_ylabel("LAI", color="tab:green")
    ax1.tick_params(axis="y", labelcolor="tab:green")
    ax2 = ax1.twinx()
    ax2.plot(x, biomass, label="Biomass (g m^-2)", color="tab:blue")
    ax2.set_ylabel("Biomass (g m^-2)", color="tab:blue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")
    if show_ribbon and stages:

        def stage_color(s: PhenologyStage) -> str:
            return {
                PhenologyStage.PLANTED: "#f0f0f0",
                PhenologyStage.EMERGED: "#e0ffe0",
                PhenologyStage.VEGETATIVE: "#c8f7c5",
                PhenologyStage.FLOWERING: "#ffe6a3",
                PhenologyStage.GRAIN_FILL: "#ffd6cc",
                PhenologyStage.MATURITY: "#dddddd",
            }.get(s, "#eeeeee")

        start = 0
        for i in range(1, len(stages) + 1):
            if i == len(stages) or stages[i] != stages[start]:
                ax1.axvspan(
                    start + 1,
                    i,
                    color=stage_color(stages[start]),
                    alpha=0.25,
                    linewidth=0,
                )
                start = i
    y_top = max(lai) if lai else 1.0
    for d, label in stage_marks:
        if 1 <= d <= days:
            ax1.axvline(d, color="gray", linestyle=":", linewidth=0.8)
            ax1.text(
                d,
                y_top * 0.98,
                label,
                rotation=90,
                ha="center",
                va="top",
                fontsize=8,
                color="gray",
            )
    fig.suptitle(f"Phenology & Canopy – {pattern}")
    fig.tight_layout()
    plt.savefig(out, dpi=150)
    # Efficiency plot
    import numpy as np

    intercepted_np = np.array(intercepted)
    biomass_inc_np = np.array(biomass_inc)
    with np.errstate(divide="ignore", invalid="ignore"):
        eff = np.where(intercepted_np > 1e-9, biomass_inc_np / intercepted_np, 0.0)
    win = 7
    kernel = np.ones(win) / win
    eff_ma = np.convolve(eff, kernel, mode="same")
    plt.figure(figsize=(10, 4))
    plt.plot(x, eff_ma, label="RUE effective (g/MJ)")
    plt.ylabel("g biomass per MJ PAR")
    plt.xlabel("Day")
    plt.title("Effective RUE (7-day MA)")
    plt.tight_layout()
    plt.savefig(efficiency_out, dpi=150)
    # Phase plot
    plt.figure(figsize=(6, 6))
    plt.plot(lai, biomass, marker=".")
    plt.xlabel("LAI")
    plt.ylabel("Biomass (g m^-2)")
    plt.title("LAI vs Biomass phase plot")
    plt.tight_layout()
    plt.savefig(phase_out, dpi=150)


def simulate_roots(
    profile_name: str,
    days: int,
    growth_rate_cm_per_day: float,
    max_depth_cm: float,
    distribution: str,
) -> tuple[List[float], List[float], List[List[float]]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    bus = EventBus()
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
    roots = RootModule(
        RootParams(
            growth_rate_cm_per_day=growth_rate_cm_per_day,
            max_depth_cm=max_depth_cm,
            distribution=distribution,
        ),
        event_bus=bus,
    )
    state = RootState()
    depths: List[float] = []
    top_frac: List[float] = []
    fractions_over_time: List[List[float]] = []
    for _ in range(days):
        phen.update_daily(tmin_c=10.0, tmax_c=20.0, photoperiod_h=12.0)
        _ = roots.daily_step(state, profile, phen.state.stage)
        depths.append(state.current_depth_cm)
        if state.layer_fractions:
            top_frac.append(state.layer_fractions[0])
            fractions_over_time.append(list(state.layer_fractions))
        else:
            top_frac.append(0.0)
            fractions_over_time.append([])
    return depths, top_frac, fractions_over_time


def plot_roots_timeseries(
    profile: str,
    days: int,
    rate: float,
    max_depth: float,
    dist: str,
    out: Path,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    depths, top_frac, fractions_over_time = simulate_roots(
        profile_name=profile,
        days=days,
        growth_rate_cm_per_day=rate,
        max_depth_cm=max_depth,
        distribution=dist,
    )
    x = list(range(1, days + 1))
    fig, ax = plt.subplots(3, 1, figsize=(10, 10), sharex=True)
    ax[0].plot(x, depths, label="root depth (cm)")
    ax[0].set_ylabel("Depth (cm)")
    ax[0].legend()
    ax[0].set_title(f"Root development – {profile} ({dist})")
    ax[1].plot(x, top_frac, label="top-layer fraction")
    ax[1].set_ylabel("Fraction (0-1)")
    ax[1].set_xlabel("Day")
    ax[1].legend()
    if any(frac for frac in fractions_over_time):
        max_layers = max((len(f) for f in fractions_over_time), default=0)
        show_layers = min(5, max_layers)
        stacked = [
            [(f[i] if i < len(f) else 0.0) for f in fractions_over_time]
            for i in range(show_layers)
        ]
        labels = [f"layer {i}" for i in range(show_layers)]
        ax[2].stackplot(x, *stacked, labels=labels)
        ax[2].set_ylabel("Layer fraction")
        ax[2].set_xlabel("Day")
        ax[2].legend(loc="upper right", ncol=min(5, show_layers))
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print("Saved", out)
