from __future__ import annotations

import argparse
import csv
import subprocess
from math import sin, pi
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.phenology import PhenologyStage
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series
from agrogame.weather.constants import DEFAULT_ALBEDO
from agrogame.weather.module import WeatherModule
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.weather.types import WeatherRecord, WeatherSeries
from agrogame.soil.water.events import EvaporationTaken, TranspirationByLayer
from agrogame.plant.events import WaterStressComputed, NutrientStressComputed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot integrated modules over time")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/full_integration.png"))
    parser.add_argument("--ph", type=float, default=6.8, help="Base soil pH")
    parser.add_argument(
        "--ph-pattern",
        choices=["constant", "acidify", "alkalize"],
        default="constant",
        help="Trend of soil pH over time for visualization",
    )
    parser.add_argument(
        "--p-fert", type=str, default="", help="Comma ops day:kg/ha, e.g. '10:20,40:15'"
    )
    parser.add_argument(
        "--lime", type=str, default="", help="Comma ops day:kg/ha, e.g. '5:1000'"
    )
    parser.add_argument(
        "--residue",
        type=float,
        default=0.0,
        help="Residue cover fraction (0-1) to reduce soil evaporation",
    )
    parser.add_argument(
        "--crop",
        type=str,
        default=None,
        help="Crop preset name (e.g. maize, wheat, grape)",
    )
    add_weather_args(parser)
    parser.add_argument(
        "--alt-weather",
        action="store_true",
        help="Use variable weather (sinusoidal temps/PAR, pulsed rain)",
    )
    parser.add_argument(
        "--n-demand",
        type=float,
        default=1.5,
        help="Base plant N demand (kg/ha·d); scaled by biomass increment",
    )
    parser.add_argument(
        "--p-demand",
        type=float,
        default=0.3,
        help="Base plant P demand (kg/ha·d); scaled by biomass increment",
    )
    return parser


def _parse_ops(spec: str) -> list[tuple[int, float]]:
    ops: list[tuple[int, float]] = []
    if not spec:
        return ops
    for part in spec.split(","):
        if ":" in part:
            d, v = part.split(":", 1)
            ops.append((int(d.strip()), float(v.strip())))
    return ops


def _par_from_record(rec: WeatherRecord) -> float:
    """Extract PAR from a weather record, deriving from shortwave if needed."""
    if rec.net_radiation_mj_m2 is not None:
        return max(0.0, rec.net_radiation_mj_m2)
    albedo = rec.albedo if rec.albedo is not None else DEFAULT_ALBEDO
    sw = rec.shortwave_mj_m2 or 0.0
    return max(0.0, sw * max(0.0, 1.0 - albedo))


def _weather_from_series(
    rec: WeatherRecord,
) -> tuple[float, float, float, float, float, float]:
    tmin, tmax = rec.tmin_c, rec.tmax_c
    par = _par_from_record(rec)
    wind = rec.wind_m_s or 2.0
    rh = rec.relative_humidity_pct or 60.0
    rain = rec.precip_mm or 0.0
    return tmin, tmax, par, rain, wind, rh


def _resolve_weather_for_day(
    day: int,
    auto_series: WeatherSeries | None,
    alt_weather: bool,
) -> tuple[float, float, float, float, float, float]:
    """Return (tmin, tmax, par, rain, wind, rh) for a single day."""
    if auto_series is not None and day < len(auto_series.records):
        return _weather_from_series(auto_series.records[day])
    if alt_weather:
        tmin = 8.0 + 4.0 * sin(2 * pi * day / 30.0)
        tmax = 20.0 + 6.0 * sin(2 * pi * day / 30.0 + 0.8)
        par = 10.0 + 6.0 * max(0.0, sin(2 * pi * day / 15.0))
        rain = 8.0 if (day % 11 in (0, 1)) else 0.0
        return tmin, tmax, par, rain, 2.0, 60.0
    return 10.0, 22.0, 12.0, 3.0, 2.0, 60.0


def _compute_target_ph(ph_pattern: str, base_ph: float, day: int) -> float:
    if ph_pattern == "acidify":
        return max(4.5, base_ph - 0.01 * day)
    if ph_pattern == "alkalize":
        return min(8.5, base_ph + 0.01 * day)
    return base_ph


def _apply_scheduled_ops(
    day: int,
    p_ops: list[tuple[int, float]],
    lime_ops: list[tuple[int, float]],
    orch: FullSimulationOrchestrator,
) -> None:
    from agrogame.soil.chemistry.events import LimeApplied

    for d, amt in p_ops:
        if d == day:
            orch.p_cycle.apply_triple_superphosphate(layer=0, amount_kg_ha=amt)
    for d, amt in lime_ops:
        if d == day:
            orch.event_bus.emit(LimeApplied(layer=0, rate_kg_ha=amt))


def _collect_day_history(
    orch: FullSimulationOrchestrator,
    et_mod: Evapotranspiration,
    histories: dict,
    tmin: float,
    tmax: float,
    rh: float,
    wind: float,
    par: float,
    ws_last: float | None,
    n_last: float | None,
    p_last: float | None,
    agg_evap: float,
    agg_transp: float,
) -> None:
    histories["stage_series"].append(orch.phenology.state.stage)
    histories["lai"].append(orch.canopy.state.lai)
    histories["biomass"].append(orch.canopy.state.biomass_g_m2)
    histories["grain_biomass"].append(orch.canopy.state.grain_biomass_g_m2)
    try:
        histories["root_depth"].append(orch.root_state.current_depth_cm)
    except Exception:
        histories["root_depth"].append(0.0)
    histories["ph_top"].append(orch.chem.ph_by_layer[0])
    histories["p_fix_today"].append(0.0)
    histories["p_avail_top"].append(orch.p_state.available_p[0])
    histories["water_stress"].append(ws_last)
    histories["n_stress"].append(n_last)
    histories["p_stress"].append(p_last)
    histories["micro_c"].append(
        sum(layer_state.c_kg_ha for layer_state in orch.microbes.state.layers)
    )
    histories["micro_n"].append(
        sum(layer_state.n_kg_ha for layer_state in orch.microbes.state.layers)
    )
    histories["enzyme_cost"].append(0.1 * 5.0)
    histories["tmins"].append(tmin)
    histories["tmaxs"].append(tmax)
    histories["rhs"].append(rh)
    histories["winds"].append(wind)
    histories["rads"].append(par)
    tmean = 0.5 * (tmin + tmax)
    histories["et0_pm_series"].append(
        et_mod.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=par,
            method="penman-monteith",
            wind_m_s=wind,
            relative_humidity_pct=rh,
        )
    )
    comps = et_mod.potential_components(
        et0_mm=histories["et0_pm_series"][-1],
        lai=orch.canopy.state.lai,
    )
    histories["pot_transp_series"].append(comps.potential_transp_mm)
    histories["evap_mm_series"].append(agg_evap)
    histories["transp_mm_series"].append(agg_transp)


def _ffill_clamp(vals: list[float], lo: float, hi: float) -> list[float]:
    out: list[float] = []
    last: float | None = None
    for v in vals:
        vv = v
        if vv < lo or vv > hi:
            vv = last if last is not None else max(lo, min(0.0, hi))
        out.append(vv)
        last = vv
    return out


def _sanitize(seq: list[float | None]) -> list[float]:
    out: list[float] = []
    for v in seq:
        if v is None:
            out.append(float("nan"))
        else:
            try:
                out.append(float(v))
            except Exception:
                out.append(float("nan"))
    return out


def _setup_figure(total_days: int) -> tuple:
    x = list(range(1, total_days + 1))
    fig = plt.figure(figsize=(12, 16), constrained_layout=True)
    gs = fig.add_gridspec(
        7,
        2,
        height_ratios=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.14],
        hspace=0.05,
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
    ax_s = fig.add_subplot(gs[5, 1], sharex=wx0)
    ax_legend = fig.add_subplot(gs[6, :])
    ax_legend.axis("off")
    ax = [[ax10, ax11], [ax20, ax21], [ax30, ax31]]
    return x, fig, wx0, wx1, ax, ax30, ax31, ax50, ax_s, ax_legend


def _plot_panels(
    x: list,
    h: dict,
    total_days: int,
    wx0: Any,
    wx1: Any,
    ax: list,
    ax30: Any,
    ax31: Any,
    ax50: Any,
    ax_s: Any,
    ax_legend: Any,
    stage_series: list,
    args: argparse.Namespace,
) -> None:
    tmins = _ffill_clamp(h["tmins"], -60.0, 60.0)
    tmaxs = _ffill_clamp(h["tmaxs"], -60.0, 60.0)
    rhs = _ffill_clamp(h["rhs"], 0.0, 100.0)
    winds = _ffill_clamp(h["winds"], 0.0, 60.0)

    wx0.plot(x, tmins, label="Tmin (°C)")
    wx0.plot(x, tmaxs, label="Tmax (°C)")
    wx0b = wx0.twinx()
    wx0b.plot(x, rhs, ":", label="RH (%)")
    wx0b.plot(x, winds, "--", label="Wind (m/s)")
    wx0.set_title("Weather drivers")
    wx0.legend(loc="upper left")
    wx1.plot(x, h["rads"], label="Radiation (MJ m⁻²)")

    _plot_water_fluxes(x, h, total_days, ax[0][0])
    _plot_canopy(x, h, ax[0][1])
    _plot_phenology_stages(x, stage_series, total_days, ax[1][0])
    _plot_roots(x, h, ax[1][1])
    _plot_nitrogen(x, ax[2][0])
    _plot_et_overview(x, h, ax[2][1])
    _plot_phosphorus(x, h, ax30)
    _plot_stress(x, h, ax_s)
    _plot_microbes(x, h, ax31)
    _plot_soil_ph(x, h, ax50, args)

    _add_combined_legend(wx0, wx1, ax, ax30, ax31, ax_s, ax50, ax_legend, total_days)


def _plot_water_fluxes(x: list, h: dict, total_days: int, ax_w: Any) -> None:
    ax_w.plot(x, [0.0] * total_days, label="Runoff (mm)")
    ax_w.plot(x, [0.0] * total_days, label="Deep drainage (mm)")
    ax_w.plot(x, h["evap_mm_series"], label="Evaporation (mm)")
    ax_w.set_title("Water fluxes")
    ax_w2 = ax_w.twinx()
    ax_w2.plot(x, [0.0] * total_days, "k:", label="ΔStorage (mm)")
    ax_w2.set_ylabel("ΔStorage (mm)")


def _plot_canopy(x: list, h: dict, ax: Any) -> None:
    ax.plot(x, h["lai"], label="LAI (-)")
    ax.plot(x, h["biomass"], label="Biomass (g/m²)")
    ax.set_title("Canopy development")


def _plot_phenology_stages(
    x: list, stage_series: list, total_days: int, ax: Any
) -> None:
    ax.set_title("Phenology stages")
    stage_colors = {
        "planted": "#9ecae1",
        "emerged": "#a1d99b",
        "vegetative": "#74c476",
        "flowering": "#fd8d3c",
        "grain_fill": "#fdd0a2",
        "maturity": "#bcbddc",
    }
    t_days: list[int] = [1]
    t_labels: list[str] = [stage_series[0].name] if stage_series else ["emerged"]
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
        ax.broken_barh(
            [(start_day, length)],
            (0, 1),
            facecolors=stage_colors.get(label_name, plt.get_cmap("tab10")(i % 10)),
        )
    ax.set_ylim(0, 1)
    ax.set_yticks([])


def _plot_roots(x: list, h: dict, ax: Any) -> None:
    root_depth = h["root_depth"]
    ax.plot(
        x,
        root_depth if root_depth else [0.0] * len(x),
        label="Root depth (cm)",
    )
    ax.set_title("Root depth")


def _plot_nitrogen(x: list, ax: Any) -> None:
    ax.plot(x, [0.0] * len(x), label="NO₃ top (kg/ha)")
    ax_n2 = ax.twinx()
    ax_n2.bar(
        x,
        [0.0] * len(x),
        alpha=0.25,
        color="#2ca02c",
        label="Mass-flow uptake (kg/ha·d)",
    )
    ax.set_title("Nitrogen: NO3 (top) and mass-flow uptake")


def _plot_et_overview(x: list, h: dict, ax: Any) -> None:
    ax.plot(x, h["et0_pm_series"], label="ET₀ PM (mm)")
    ax.plot(x, h["evap_mm_series"], label="Actual Evap (mm)")
    ax.plot(x, h["transp_mm_series"], label="Actual Transp (mm)")


def _plot_phosphorus(x: list, h: dict, ax_p: Any) -> None:
    ax_p.plot(x, h["p_avail_top"], label="Available P top (kg/ha)")
    ax_p2 = ax_p.twinx()
    ax_p2.bar(
        x, h["p_fix_today"], alpha=0.25, color="#9467bd", label="Fixation (kg/ha·d)"
    )
    ax_p.set_title("Phosphorus: available (top) and fixation")


def _plot_stress(x: list, h: dict, ax_s: Any) -> None:
    ax_s.plot(x, _sanitize(h["water_stress"]), label="Water stress (-)")
    if any(v is not None for v in h["n_stress"]):
        ax_s.plot(x, _sanitize(h["n_stress"]), label="N stress (-)")
    if any(v is not None for v in h["p_stress"]):
        ax_s.plot(x, _sanitize(h["p_stress"]), label="P stress (-)")
    ax_s.set_ylim(0.0, 1.05)
    ax_s.set_title("Stress factors")


def _plot_microbes(x: list, h: dict, ax_m: Any) -> None:
    ax_m.plot(x, h["micro_c"], label="Microbial C (kg/ha)")
    ax_m.plot(x, h["micro_n"], label="Microbial N (kg/ha)")
    ax_m2 = ax_m.twinx()
    ax_m2.bar(
        x,
        h["enzyme_cost"],
        alpha=0.25,
        color="#7f7f7f",
        label="Enzyme cost C (kg/ha·d)",
    )
    ax_m.set_title("Microbes: biomass and enzyme cost")


def _plot_soil_ph(x: list, h: dict, ax50: Any, args: argparse.Namespace) -> None:
    ax50.plot(x, h["ph_top"] if h["ph_top"] else [args.ph] * len(x), label="pH (top)")
    ax50.set_ylim(4.0, 9.0)
    ax50.set_title("Soil pH (top layer)")


def _add_combined_legend(
    wx0: Any,
    wx1: Any,
    ax: list,
    ax30: Any,
    ax31: Any,
    ax_s: Any,
    ax50: Any,
    ax_legend: Any,
    total_days: int,
) -> None:
    # Collect all handles/labels from axes that have twin axes
    all_axes = [
        wx0,
        wx1,
        ax[0][0],
        ax[0][1],
        ax[1][0],
        ax[1][1],
        ax[2][0],
        ax[2][1],
        ax30,
        ax31,
        ax_s,
        ax50,
    ]
    # Also include twin axes
    for a in list(all_axes):
        for child in getattr(a, "child_axes", []):
            all_axes.append(child)

    handles, labels = [], []
    for a in all_axes:
        h_ax, l_ax = a.get_legend_handles_labels()
        handles.extend(h_ax)
        labels.extend(l_ax)
    seen = set()
    uniq_handles, uniq_labels = [], []
    for handle, lbl in zip(handles, labels, strict=False):
        if lbl and lbl not in seen:
            seen.add(lbl)
            uniq_handles.append(handle)
            uniq_labels.append(lbl)
    ax_legend.legend(uniq_handles, uniq_labels, loc="center", ncol=5, frameon=False)

    for col in range(2):
        ax[2][col].set_xlabel("Day")


def _export_csv(args: argparse.Namespace, h: dict, total_days: int) -> Path:
    out_path: Path = args.out
    base_noext = out_path.with_suffix("")
    csv_name = "full_integration_timeseries.csv"
    csv_path: Path = base_noext.with_name(csv_name)
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "day",
                "lai",
                "biomass_g_m2",
                "grain_biomass_g_m2",
                "biomass_inc_g_m2",
                "evap_mm",
                "transp_mm",
                "pot_transp_mm",
                "et0_mm",
                "water_stress",
                "n_stress",
                "p_stress",
                "p_avail_top_kg_ha",
                "root_depth_cm",
                "stage",
            ]
        )
        prev_b = 0.0
        for i in range(total_days):
            b = h["biomass"][i]
            inc = max(0.0, b - prev_b)
            prev_b = b
            stg = h["stage_series"][i]
            stage_str = stg.name if hasattr(stg, "name") else str(stg)
            writer.writerow(
                [
                    i + 1,
                    h["lai"][i],
                    b,
                    h["grain_biomass"][i] if h.get("grain_biomass") else 0.0,
                    inc,
                    h["evap_mm_series"][i],
                    h["transp_mm_series"][i],
                    h["pot_transp_series"][i],
                    h["et0_pm_series"][i],
                    (h["water_stress"][i] if h["water_stress"][i] is not None else ""),
                    (h["n_stress"][i] if h["n_stress"][i] is not None else ""),
                    (h["p_stress"][i] if h["p_stress"][i] is not None else ""),
                    h["p_avail_top"][i] if h["p_avail_top"] else "",
                    h["root_depth"][i] if h["root_depth"] else 0.0,
                    stage_str,
                ]
            )
    print(f"Saved {csv_path}")
    return csv_path


def _init_history() -> dict:
    return {
        k: []
        for k in [
            "lai",
            "biomass",
            "stage_series",
            "root_depth",
            "p_avail_top",
            "p_fix_today",
            "ph_top",
            "water_stress",
            "n_stress",
            "p_stress",
            "micro_c",
            "micro_n",
            "enzyme_cost",
            "tmins",
            "tmaxs",
            "rhs",
            "winds",
            "rads",
            "et0_pm_series",
            "evap_mm_series",
            "transp_mm_series",
            "pot_transp_series",
        ]
    }


def _run_simulation_loop(
    args: argparse.Namespace,
    orch: FullSimulationOrchestrator,
    auto_series: WeatherSeries | None,
    weather_module: WeatherModule | None,
    h: dict,
    total_days: int,
) -> None:
    p_ops = _parse_ops(args.p_fert)
    lime_ops = _parse_ops(args.lime)
    et_mod = Evapotranspiration(EtParams())

    ws_last: float | None = None
    n_last: float | None = None
    p_last: float | None = None

    def _on_ws(ev: WaterStressComputed) -> None:
        nonlocal ws_last
        ws_last = float(ev.stress)

    def _on_ns(ev: NutrientStressComputed) -> None:
        nonlocal n_last, p_last
        name = str(ev.nutrient).upper()
        if name == "N":
            n_last = float(ev.stress)
        elif name == "P":
            p_last = float(ev.stress)

    orch.event_bus.subscribe(WaterStressComputed, _on_ws)
    orch.event_bus.subscribe(NutrientStressComputed, _on_ns)

    agg_evap = 0.0
    agg_transp = 0.0

    def _on_evap(ev: EvaporationTaken) -> None:
        nonlocal agg_evap
        agg_evap += float(ev.amount_mm)

    def _on_transp(ev: TranspirationByLayer) -> None:
        nonlocal agg_transp
        total = float(getattr(ev, "total_mm", sum(ev.amounts_mm)))
        agg_transp += total

    orch.event_bus.subscribe(EvaporationTaken, _on_evap)
    orch.event_bus.subscribe(TranspirationByLayer, _on_transp)

    from datetime import timedelta

    # Determine simulation start date from weather series or CLI
    if auto_series and auto_series.records:
        sim_start = auto_series.records[0].day
    else:
        start_str = getattr(args, "start_date", None)
        if start_str:
            from datetime import datetime as _dt

            sim_start = _dt.strptime(start_str, "%Y-%m-%d").date()
        else:
            from datetime import date as _d

            sim_start = _d(_d.today().year, 1, 1)

    for day in range(total_days):
        sim_date = sim_start + timedelta(days=day)
        tmin, tmax, par, rain, wind, rh = _resolve_weather_for_day(
            day, auto_series, args.alt_weather
        )
        if auto_series and day < len(auto_series.records) and weather_module:
            _ = weather_module.emit_for_day(day)

        target_ph = _compute_target_ph(args.ph_pattern, args.ph, day)
        _apply_scheduled_ops(day, p_ops, lime_ops, orch)

        d_biomass = _biomass_delta(h["biomass"])
        biomass_kg_ha = d_biomass * 0.01
        n_demand = float(args.n_demand) * (1.0 + 0.5 * (biomass_kg_ha > 0))
        p_demand = float(args.p_demand) * (1.0 + 0.5 * (biomass_kg_ha > 0))

        agg_evap = 0.0
        agg_transp = 0.0

        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=par,
            sim_date=sim_date,
            target_ph=target_ph,
            plant_n_demand_kg_ha=n_demand,
            plant_p_demand_kg_ha=p_demand,
        )

        _collect_day_history(
            orch,
            et_mod,
            h,
            tmin,
            tmax,
            rh,
            wind,
            par,
            ws_last,
            n_last,
            p_last,
            agg_evap,
            agg_transp,
        )


def _biomass_delta(biomass_list: list[float]) -> float:
    if not biomass_list:
        return 0.0
    prev_b: float = biomass_list[-2] if len(biomass_list) > 1 else 0.0
    return max(0.0, biomass_list[-1] - prev_b)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[args.profile]

    plt.style.use("ggplot")
    et_params = EtParams(residue_cover_fraction=max(0.0, min(1.0, args.residue)))
    crop_preset = None
    if getattr(args, "crop", None):
        from agrogame.plant.presets import load_crop_presets

        crop_lib = load_crop_presets()
        if args.crop not in crop_lib.crops:
            raise ValueError(
                f"Unknown crop {args.crop!r}; "
                f"available: {sorted(crop_lib.crops.keys())}"
            )
        crop_preset = crop_lib.crops[args.crop]
    orch = FullSimulationOrchestrator(profile, et_params=et_params, crop=crop_preset)

    auto_series = get_weather_series(args, args.days)
    if auto_series is not None:
        auto_series = sanitize_weather_series(auto_series)
    weather_module = WeatherModule(auto_series, orch.event_bus) if auto_series else None

    h = _init_history()
    total_days = (
        args.days if auto_series is None else min(args.days, len(auto_series.records))
    )

    _run_simulation_loop(args, orch, auto_series, weather_module, h, total_days)

    # Plotting
    x, fig, wx0, wx1, ax, ax30, ax31, ax50, ax_s, ax_legend = _setup_figure(total_days)
    _plot_panels(
        x,
        h,
        total_days,
        wx0,
        wx1,
        ax,
        ax30,
        ax31,
        ax50,
        ax_s,
        ax_legend,
        h["stage_series"],
        args,
    )
    fig.savefig(args.out, dpi=150, bbox_inches="tight", pad_inches=0.2)
    print(f"Saved {args.out}")

    csv_path = _export_csv(args, h, total_days)

    report_name = "expectations_full_integration.md"
    report_path = args.out.with_suffix("").with_name(report_name)
    cmd = [
        "python",
        "scripts/check_expectations.py",
        "--timeseries",
        str(csv_path),
        "--out",
        str(report_path),
    ]
    subprocess.run(cmd, check=False)
    print(f"Wrote expectations report: {report_path}")


if __name__ == "__main__":
    main()
