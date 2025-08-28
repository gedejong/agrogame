from __future__ import annotations

import argparse
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


def _seasonal_series(days: int, base: float, amp: float, period: int) -> List[float]:
    import math

    return [
        base + amp * math.sin(2 * math.pi * (i / max(1, period))) for i in range(days)
    ]


def simulate_phenology_canopy(
    days: int,
    tmin: float,
    tmax: float,
    par: float,
    pattern: str,
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

    # Collect stage changes (day index, label) for annotations
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
        tmins = _seasonal_series(days, tmin, amp=5.0, period=30)
        tmaxs = _seasonal_series(days, tmax, amp=7.0, period=30)
        pars = _seasonal_series(days, par, amp=0.5 * par, period=30)
    else:
        tmins = [tmin] * days
        tmaxs = [tmax] * days
        pars = [par] * days

    for i in range(days):
        state = pheno.update_daily(tmin_c=tmins[i], tmax_c=tmaxs[i], photoperiod_h=12.0)
        stages.append(state.stage)
        fx = canopy.daily_step(
            incident_par_mj_m2=pars[i], temp_factor=1.0, water_stress=1.0, n_stress=1.0
        )
        intercepted_series.append(fx.intercepted_par_mj_m2)
        biomass_inc_series.append(fx.biomass_increment_g_m2)
        lai.append(canopy.state.lai)
        biomass.append(canopy.state.biomass_g_m2)

    return (
        lai,
        biomass,
        stages,
        stage_marks,
        intercepted_series,
        biomass_inc_series,
    )


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

    args.out.parent.mkdir(parents=True, exist_ok=True)

    (
        lai,
        biomass,
        stages,
        stage_marks,
        intercepted,
        biomass_inc,
    ) = simulate_phenology_canopy(
        days=args.days,
        tmin=args.tmin,
        tmax=args.tmax,
        par=args.par,
        pattern=args.pattern,
    )

    x = list(range(1, args.days + 1))
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.plot(x, lai, label="LAI", color="tab:green")
    ax1.set_xlabel("Day")
    ax1.set_ylabel("LAI", color="tab:green")
    ax1.tick_params(axis="y", labelcolor="tab:green")

    ax2 = ax1.twinx()
    ax2.plot(x, biomass, label="Biomass (g m^-2)", color="tab:blue")
    ax2.set_ylabel("Biomass (g m^-2)", color="tab:blue")
    ax2.tick_params(axis="y", labelcolor="tab:blue")

    # Optional: shaded stage ribbons
    if args.show_ribbon and stages:
        # Find contiguous spans of the same stage
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

    # Add phenology event markers and labels
    y_top = max(lai) if lai else 1.0
    for d, label in stage_marks:
        if 1 <= d <= args.days:
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

    fig.suptitle(f"Phenology & Canopy – {args.pattern}")
    fig.tight_layout()
    plt.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")

    # Efficiency plot: rolling biomass_increment / intercepted_PAR
    import numpy as np

    intercepted_np = np.array(intercepted)
    biomass_inc_np = np.array(biomass_inc)
    with np.errstate(divide="ignore", invalid="ignore"):
        eff = np.where(intercepted_np > 1e-9, biomass_inc_np / intercepted_np, 0.0)
    # 7-day moving average
    win = 7
    kernel = np.ones(win) / win
    eff_ma = np.convolve(eff, kernel, mode="same")

    plt.figure(figsize=(10, 4))
    plt.plot(x, eff_ma, label="RUE effective (g/MJ)")
    plt.ylabel("g biomass per MJ PAR")
    plt.xlabel("Day")
    plt.title("Effective RUE (7-day MA)")
    plt.tight_layout()
    plt.savefig(args.efficiency_out, dpi=150)
    print(f"Saved {args.efficiency_out}")

    # Phase plot: LAI vs Biomass
    plt.figure(figsize=(6, 6))
    plt.plot(lai, biomass, marker=".")
    plt.xlabel("LAI")
    plt.ylabel("Biomass (g m^-2)")
    plt.title("LAI vs Biomass phase plot")
    plt.tight_layout()
    plt.savefig(args.phase_out, dpi=150)
    print(f"Saved {args.phase_out}")


if __name__ == "__main__":
    main()
