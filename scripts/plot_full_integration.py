from __future__ import annotations

import argparse
from pathlib import Path
from math import sin, pi
from typing import List

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.phenology import PhenologyStage
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series
from agrogame.weather.constants import DEFAULT_ALBEDO
from agrogame.weather.module import WeatherModule


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot integrated modules over time")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/full_integration.png"))
    # Soil pH visualization and effects controls
    parser.add_argument("--ph", type=float, default=6.8, help="Base soil pH")
    parser.add_argument(
        "--ph-pattern",
        choices=["constant", "acidify", "alkalize"],
        default="constant",
        help="Trend of soil pH over time for visualization",
    )
    # Nutrient schedules
    parser.add_argument(
        "--p-fert", type=str, default="", help="Comma ops day:kg/ha, e.g. '10:20,40:15'"
    )
    parser.add_argument(
        "--lime", type=str, default="", help="Comma ops day:kg/ha, e.g. '5:1000'"
    )
    add_weather_args(parser)
    parser.add_argument(
        "--alt-weather",
        action="store_true",
        help="Use variable weather (sinusoidal temps/PAR, pulsed rain)",
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    plt.style.use("ggplot")
    orch = FullSimulationOrchestrator(profile)

    # Optional external weather time series
    auto_series = get_weather_series(args, args.days)
    if auto_series is not None:
        auto_series = sanitize_weather_series(auto_series)
    weather_module = WeatherModule(auto_series, orch.event_bus) if auto_series else None

    # Time series
    lai: List[float] = []
    biomass: List[float] = []
    stage_series: List[PhenologyStage] = []
    root_depth: List[float] = []
    p_avail_top: List[float] = []
    p_fix_today: List[float] = []
    ph_top: List[float] = []
    # Microbes
    micro_c: List[float] = []
    micro_n: List[float] = []
    enzyme_cost: List[float] = []

    # Weather diagnostics
    tmins: List[float] = []
    tmaxs: List[float] = []
    rhs: List[float] = []
    winds: List[float] = []
    rads: List[float] = []

    # Helpers
    def _parse_ops(spec: str) -> list[tuple[int, float]]:
        ops: list[tuple[int, float]] = []
        if not spec:
            return ops
        for part in spec.split(","):
            if ":" in part:
                d, v = part.split(":", 1)
                try:
                    ops.append((int(d.strip()), float(v.strip())))
                except Exception:
                    continue
        return ops

    p_ops = _parse_ops(args.p_fert)
    lime_ops = _parse_ops(args.lime)

    total_days = (
        args.days if auto_series is None else min(args.days, len(auto_series.records))
    )

    # Local imports for scheduled events
    from agrogame.soil.chemistry.events import LimeApplied

    for day in range(total_days):
        # Weather drivers
        if auto_series and day < len(auto_series.records):
            rec = auto_series.records[day]
            tmin, tmax = rec.tmin_c, rec.tmax_c
            if rec.net_radiation_mj_m2 is not None:
                par = rec.net_radiation_mj_m2
            else:
                albedo = (
                    rec.albedo
                    if getattr(rec, "albedo", None) is not None
                    else DEFAULT_ALBEDO
                )
                sw = rec.shortwave_mj_m2 or 0.0
                par = sw * max(0.0, 1.0 - albedo)
            par = max(0.0, par)
            wind = rec.wind_m_s or 2.0
            rh = rec.relative_humidity_pct or 60.0
            rain = 0.0
            if weather_module:
                _ = weather_module.emit_for_day(day)
        elif args.alt_weather:
            tmin = 8.0 + 4.0 * sin(2 * pi * day / 30.0)
            tmax = 20.0 + 6.0 * sin(2 * pi * day / 30.0 + 0.8)
            par = 10.0 + 6.0 * max(0.0, sin(2 * pi * day / 15.0))
            rain = 8.0 if (day % 11 in (0, 1)) else 0.0
            wind = 2.0
            rh = 60.0
        else:
            tmin, tmax, par = 10.0, 22.0, 12.0
            rain = 3.0
            wind = 2.0
            rh = 60.0

        # pH trend via chemistry buffering
        if args.ph_pattern == "acidify":
            target_ph = max(4.5, args.ph - 0.01 * day)
        elif args.ph_pattern == "alkalize":
            target_ph = min(8.5, args.ph + 0.01 * day)
        else:
            target_ph = args.ph

        # Scheduled operations
        for d, amt in p_ops:
            if d == day:
                orch.p_cycle.apply_triple_superphosphate(layer=0, amount_kg_ha=amt)
        for d, amt in lime_ops:
            if d == day:
                orch.event_bus.emit(LimeApplied(layer=0, rate_kg_ha=amt))

        # Advance orchestrator (this emits events and advances N/P/water/chemistry)
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=par,
            target_ph=target_ph,
        )

        # Collect histories for plotting
        stage_series.append(orch.phenology.state.stage)
        lai.append(orch.canopy.state.lai)
        biomass.append(orch.canopy.state.biomass_g_m2)
        ph_top.append(orch.chem.ph_by_layer[0])
        p_fix_today.append(0.0)  # not tracked here; keep placeholder for layout
        p_avail_top.append(orch.p_state.available_p[0])
        # Microbes
        micro_c.append(
            sum(layer_state.c_kg_ha for layer_state in orch.microbes.state.layers)
        )
        micro_n.append(
            sum(layer_state.n_kg_ha for layer_state in orch.microbes.state.layers)
        )
        enzyme_cost.append(0.1 * 5.0)  # matches placeholder in module
        # Weather histories
        tmins.append(tmin)
        tmaxs.append(tmax)
        rhs.append(rh)
        winds.append(wind)
        rads.append(par)

    # Plotting (unchanged structure; references adjusted to orchestrator data)
    x = list(range(1, total_days + 1))
    fig = plt.figure(figsize=(12, 16), constrained_layout=True)
    gs = fig.add_gridspec(
        7, 2, height_ratios=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.14], hspace=0.05
    )
    wx0 = fig.add_subplot(gs[0, 0])
    wx1 = fig.add_subplot(gs[0, 1], sharex=wx0)
    ax10 = fig.add_subplot(gs[1, 0], sharex=wx0)
    ax11 = fig.add_subplot(gs[1, 1], sharex=wx0)
    ax20 = fig.add_subplot(gs[2, 0], sharex=wx0)
    ax21 = fig.add_subplot(gs[2, 1], sharex=wx0)
    ax30 = fig.add_subplot(gs[3, 0], sharex=wx0)
    ax31 = fig.add_subplot(gs[3, 1], sharex=wx0)
    ax50 = fig.add_subplot(gs[5, 0], sharex=wx0)
    # reserved panel (intentionally unused to preserve layout)
    fig.add_subplot(gs[5, 1], sharex=wx0)
    ax_legend = fig.add_subplot(gs[6, :])
    ax_legend.axis("off")
    ax = [[ax10, ax11], [ax20, ax21], [ax30, ax31]]

    # Weather panels
    def _ffill_clamp(vals: List[float], lo: float, hi: float) -> List[float]:
        out: List[float] = []
        last: float | None = None
        for v in vals:
            vv = v
            if vv is None or vv < lo or vv > hi:  # type: ignore[operator]
                vv = last if last is not None else max(lo, min(0.0, hi))
            out.append(vv)
            last = vv
        return out

    tmins = _ffill_clamp(tmins, -60.0, 60.0)
    tmaxs = _ffill_clamp(tmaxs, -60.0, 60.0)
    rhs = _ffill_clamp(rhs, 0.0, 100.0)
    winds = _ffill_clamp(winds, 0.0, 60.0)

    wx0.plot(x, tmins, label="Tmin (°C)")
    wx0.plot(x, tmaxs, label="Tmax (°C)")
    wx0b = wx0.twinx()
    wx0b.plot(x, rhs, ":", label="RH (%)")
    wx0b.plot(x, winds, "--", label="Wind (m/s)")
    wx0.set_title("Weather drivers")
    wx0.legend(loc="upper left")
    wx1.plot(x, rads, label="Radiation (MJ m⁻²)")

    # Water fluxes placeholder (not directly tracked here)
    ax_w = ax[0][0]
    ax_w.plot(x, [0.0] * len(x), label="Runoff (mm)")
    ax_w.plot(x, [0.0] * len(x), label="Deep drainage (mm)")
    ax_w.plot(x, [0.0] * len(x), label="Evaporation (mm)")
    ax_w.set_title("Water fluxes")
    ax_w2 = ax_w.twinx()
    ax_w2.plot(x, [0.0] * len(x), "k:", label="ΔStorage (mm)")
    ax_w2.set_ylabel("ΔStorage (mm)")

    # Canopy
    ax[0][1].plot(x, lai, label="LAI (-)")
    ax[0][1].plot(x, biomass, label="Biomass (g/m²)")
    ax[0][1].set_title("Canopy development")

    # Phenology stages
    ax[1][0].set_title("Phenology stages")
    stage_colors = {
        "planted": "#9ecae1",
        "emerged": "#a1d99b",
        "vegetative": "#74c476",
        "flowering": "#fd8d3c",
        "grain_fill": "#fdd0a2",
        "maturity": "#bcbddc",
    }
    t_days: List[int] = [1]
    t_labels: List[str] = [stage_series[0].name] if stage_series else ["emerged"]
    last_stage = stage_series[0] if stage_series else PhenologyStage.EMERGED
    for day_idx, st in enumerate(stage_series, start=1):
        if st != last_stage:
            t_days.append(day_idx)
            t_labels.append(st.name)
            last_stage = st
    t_days.append(total_days + 1)
    for i in range(len(t_labels)):
        start_day = t_days[i]
        end_day = t_days[i + 1] - 1
        length = end_day - start_day + 1
        label_name = t_labels[i]
        ax[1][0].broken_barh(
            [(start_day, length)],
            (0, 1),
            facecolors=stage_colors.get(label_name, plt.cm.tab10(i % 10)),
        )
    ax[1][0].set_ylim(0, 1)
    ax[1][0].set_yticks([])

    # Roots
    ax[1][1].plot(
        x, root_depth if root_depth else [0.0] * len(x), label="Root depth (cm)"
    )
    ax[1][1].set_title("Root depth")

    # Nitrogen placeholder (we didn't collect daily values here)
    ax[2][0].plot(x, [0.0] * len(x), label="NO₃ top (kg/ha)")
    ax_n2 = ax[2][0].twinx()
    ax_n2.bar(
        x,
        [0.0] * len(x),
        alpha=0.25,
        color="#2ca02c",
        label="Mass-flow uptake (kg/ha·d)",
    )
    ax[2][0].set_title("Nitrogen: NO3 (top) and mass-flow uptake")

    # ET overview placeholders
    ax[2][1].plot(x, [0.0] * len(x), label="ET₀ PT (mm)")
    ax[2][1].plot(x, [0.0] * len(x), label="ET₀ PM (mm)")
    ax[2][1].plot(x, [0.0] * len(x), label="Actual Evap (mm)")
    ax[2][1].plot(x, [0.0] * len(x), label="Actual Transp (mm)")

    # Phosphorus
    ax_p = ax30
    ax_p.plot(x, p_avail_top, label="Available P top (kg/ha)")
    ax_p2 = ax30.twinx()
    ax_p2.bar(x, p_fix_today, alpha=0.25, color="#9467bd", label="Fixation (kg/ha·d)")
    ax_p.set_title("Phosphorus: available (top) and fixation")

    # Microbes panel
    ax_m = ax31
    ax_m.plot(x, micro_c, label="Microbial C (kg/ha)")
    ax_m.plot(x, micro_n, label="Microbial N (kg/ha)")
    ax_m2 = ax_m.twinx()
    ax_m2.bar(
        x, enzyme_cost, alpha=0.25, color="#7f7f7f", label="Enzyme cost C (kg/ha·d)"
    )
    ax_m.set_title("Microbes: biomass and enzyme cost")

    # Soil pH panel
    ax50.plot(x, ph_top if ph_top else [args.ph] * len(x), label="pH (top)")
    ax50.set_ylim(4.0, 9.0)
    ax50.set_title("Soil pH (top layer)")

    # Legend
    handles, labels = [], []
    for a in [
        wx0,
        wx1,
        ax_w,
        ax_w2,
        ax[0][1],
        ax[1][0],
        ax[1][1],
        ax[2][0],
        ax[2][1],
        ax_p,
        ax_p2,
        ax_m,
        ax_m2,
        ax50,
    ]:
        h, labels_part = a.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(labels_part)
    seen = set()
    uniq_h, uniq_lbls = [], []
    for h, lbl in zip(handles, labels, strict=False):
        if lbl and lbl not in seen:
            seen.add(lbl)
            uniq_h.append(h)
            uniq_lbls.append(lbl)
    ax_legend.legend(uniq_h, uniq_lbls, loc="center", ncol=5, frameon=False)

    for col in range(2):
        ax[2][col].set_xlabel("Day")

    fig.savefig(args.out, dpi=150, bbox_inches="tight", pad_inches=0.2)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
