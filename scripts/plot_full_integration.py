from __future__ import annotations

import argparse
from pathlib import Path
from math import sin, pi
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
from agrogame.soil.canopy.interception import InterceptionState
from agrogame.plant.roots import RootModule, RootParams, RootState
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.weather.utils import sanitize_weather_series
from agrogame.weather.constants import DEFAULT_ALBEDO
from agrogame.weather.module import WeatherModule
from agrogame.weather.utils import vpd_kpa
from agrogame.plant.stress import compute_water_stress
from agrogame.plant.events import WaterStressComputed


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot integrated modules over time")
    parser.add_argument("--profile", default="loam_temperate")
    parser.add_argument("--days", type=int, default=120)
    parser.add_argument("--out", type=Path, default=Path("out/full_integration.png"))
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
    istate = InterceptionState()

    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(bus, nstate, water_state=wstate, profile=profile)
    etmod = Evapotranspiration(EtParams())

    # Optional external weather time series
    auto_series = get_weather_series(args, args.days)
    if auto_series is not None:
        auto_series = sanitize_weather_series(auto_series)
    weather_module = WeatherModule(auto_series, bus) if auto_series else None

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
    n_uptake_massflow: List[float] = []
    et0s: List[float] = []
    act_e: List[float] = []
    act_t: List[float] = []

    # Weather diagnostics
    tmins: List[float] = []
    tmaxs: List[float] = []
    rhs: List[float] = []
    winds: List[float] = []
    rads: List[float] = []

    # Respect available weather length to avoid trailing fallbacks
    total_days = args.days
    if auto_series is not None:
        total_days = min(args.days, len(auto_series.records))

    for day in range(total_days):
        # Weather drivers
        if auto_series and day < len(auto_series.records):
            rec = auto_series.records[day]
            tmin, tmax = rec.tmin_c, rec.tmax_c
            # Prefer provided net radiation; otherwise derive from shortwave
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
            # Sinusoidal temps and PAR, pulsed rainfall
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

        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        stage_series.append(phen.state.stage)

        # Water balance (let ET handle evaporation; set driver evap=0)
        storage_before = sum(
            wstate.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )
        # Interception: split rainfall into intercepted and throughfall
        intercepted, throughfall = istate.intercept(canopy.state.lai, rain)
        fx = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=throughfall, evaporation_mm=0.0)
        )
        runoff.append(fx.runoff_mm)
        deep.append(fx.deep_drainage_mm)
        # Evap will be accounted by ET below; record pre-ET dS for reference
        evap.append(0.0)
        dS.append(fx.storage_change_mm)

        # Canopy and biomass (water stress computed from ET later; for now placeholder)
        # Placeholder canopy update; final stress applied after ET below
        _ = canopy.daily_step(
            incident_par_mj_m2=par, temp_factor=1.0, water_stress=1.0, n_stress=1.0
        )
        biomass.append(canopy.state.biomass_g_m2)
        lai.append(canopy.state.lai)

        # Roots
        _ = roots.daily_step(rstate, profile, phen.state.stage)
        root_depth.append(rstate.current_depth_cm)

        # Nitrogen daily step (demand simplistic, root fractions from cached event)
        no3_before = list(nstate.no3)
        _ = ncycle.daily_step(temperature_c=18.0, plant_demand_kg_ha=1.0)
        n_no3_top.append(nstate.no3[0])

        # Evapotranspiration diagnostics (use canopy LAI)
        temp_mean = 0.5 * (tmin + tmax)
        et0 = etmod.priestley_taylor(temp_mean_c=temp_mean, net_radiation_mj_m2=par)
        # Use VPD-aware partitioning (stomatal closure under high VPD)
        comps = etmod.potential_components_with_vpd(
            et0_mm=et0, lai=canopy.state.lai, vpd_kpa=vpd_kpa(temp_mean, rh)
        )
        # Root fractions for transpiration (use roots if available else uniform)
        rf = (
            rstate.layer_fractions
            if rstate.layer_fractions
            else [1.0 / len(profile.layers)] * len(profile.layers)
        )
        # Evaporate from canopy store before soil evaporation
        canopy_evap = istate.evaporate(comps.potential_evap_mm)
        # Reduce soil potential evaporation by canopy evaporation already taken
        comps_adj = type(comps)(
            potential_evap_mm=max(0.0, comps.potential_evap_mm - canopy_evap),
            potential_transp_mm=comps.potential_transp_mm,
            et0_mm=comps.et0_mm,
        )
        actual = etmod.actual_et(profile, wstate, water, comps_adj, rf)
        et0s.append(et0)
        act_e.append(actual.evaporation_mm + canopy_evap)
        act_t.append(actual.transpiration_mm)
        # Update last evap value for plotting (replace 0.0)
        evap[-1] = actual.evaporation_mm
        # Recompute storage change after ET to reflect ET influence
        storage_after = sum(
            wstate.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )
        dS[-1] = storage_after - storage_before
        # Compute water stress for next day canopy update context (simple feed-forward)
        stress = compute_water_stress(
            actual.transpiration_mm, comps_adj.potential_transp_mm
        )
        # Emit stress event for downstream modules
        bus.emit(
            WaterStressComputed(
                supply_mm=actual.transpiration_mm,
                demand_mm=comps_adj.potential_transp_mm,
                stress=stress,
            )
        )
        # Apply stress-aware canopy growth for the day (second pass)
        _ = canopy.daily_step(
            incident_par_mj_m2=par,
            temp_factor=1.0,
            water_stress=stress,
            n_stress=1.0,
        )
        # Mass-flow NO3 uptake estimate from NO3 pool decrease (kg/ha) after ET day
        total_no3_before = sum(no3_before)
        total_no3_after = sum(nstate.no3)
        uptake_today = max(0.0, total_no3_before - total_no3_after)
        n_uptake_massflow.append(uptake_today)
        # collect weather for plotting
        tmins.append(tmin)
        tmaxs.append(tmax)
        rhs.append(rh)
        winds.append(wind)
        rads.append(par)

    x = list(range(1, total_days + 1))
    # Grid with weather row and legend row
    fig = plt.figure(figsize=(12, 12), constrained_layout=True)
    gs = fig.add_gridspec(5, 2, height_ratios=[1.0, 1.0, 1.0, 1.0, 0.14], hspace=0.05)
    wx0 = fig.add_subplot(gs[0, 0])
    wx1 = fig.add_subplot(gs[0, 1], sharex=wx0)
    ax10 = fig.add_subplot(gs[1, 0], sharex=wx0)
    ax11 = fig.add_subplot(gs[1, 1], sharex=wx0)
    ax20 = fig.add_subplot(gs[2, 0], sharex=wx0)
    ax21 = fig.add_subplot(gs[2, 1], sharex=wx0)
    ax30 = fig.add_subplot(gs[3, 0], sharex=wx0)
    ax31 = fig.add_subplot(gs[3, 1], sharex=wx0)
    ax_legend = fig.add_subplot(gs[4, :])
    ax_legend.axis("off")
    ax = [[ax10, ax11], [ax20, ax21], [ax30, ax31]]

    # Weather panels (sanitize series to avoid odd spikes)
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
    # Precipitation bars if available from weather series
    if (
        auto_series is not None
        and getattr(auto_series.records[0], "precip_mm", None) is not None
    ):
        prec = [rec.precip_mm or 0.0 for rec in auto_series.records[:total_days]]
        wx1.bar(x, prec, color="#1f77b4", alpha=0.15, label="Precip (mm)")
    wx1.set_title("Radiation")
    # Clamp y-limits to sensible ranges to avoid autoscale artifacts
    if tmins and tmaxs:
        ymin = min(min(tmins), min(tmaxs)) - 2.0
        ymax = max(max(tmins), max(tmaxs)) + 2.0
        if ymin < ymax:
            wx0.set_ylim(ymin, ymax)
    if rads:
        rmax = max(rads)
        wx1.set_ylim(0.0, max(1.0, rmax * 1.1))
    wx1.legend(loc="upper left")

    # Water fluxes with ΔStorage on right axis
    ax_w = ax[0][0]
    ax_w.plot(x, runoff, label="Runoff (mm)")
    ax_w.plot(x, deep, label="Deep drainage (mm)")
    ax_w.plot(x, evap, label="Evaporation (mm)")
    ax_w.set_title("Water fluxes")
    ax_w2 = ax_w.twinx()
    ax_w2.plot(x, dS, "k:", label="ΔStorage (mm)")
    ax_w2.set_ylabel("ΔStorage (mm)")

    # Canopy
    ax[0][1].plot(x, lai, label="LAI (-)")
    ax[0][1].plot(x, biomass, label="Biomass (g/m²)")
    ax[0][1].set_title("Canopy development")

    # Phenology stages as 1D colored bars
    ax[1][0].set_title("Phenology stages")
    stage_colors = {
        "planted": "#9ecae1",
        "emerged": "#a1d99b",
        "vegetative": "#74c476",
        "flowering": "#fd8d3c",
        "grain_fill": "#fdd0a2",
        "maturity": "#bcbddc",
    }
    # Build local transitions for the bars
    t_days: List[int] = [1]
    t_labels: List[str] = [stage_series[0].name]
    last_stage = stage_series[0]
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
        color = stage_colors.get(label_name, plt.cm.tab10(i % 10))
        ax[1][0].broken_barh([(start_day, length)], (0, 1), facecolors=color)
    ax[1][0].set_ylim(0, 1)
    ax[1][0].set_yticks([])

    # Roots
    ax[1][1].plot(x, root_depth, label="Root depth (cm)")
    ax[1][1].set_title("Root depth")

    # Nitrogen: NO3 top and mass-flow uptake
    ax[2][0].plot(x, n_no3_top, label="NO₃ top (kg/ha)")
    ax_n2 = ax[2][0].twinx()
    ax_n2.bar(
        x,
        n_uptake_massflow,
        alpha=0.25,
        color="#2ca02c",
        label="Mass-flow uptake (kg/ha·d)",
    )
    ax[2][0].set_title("Nitrogen: NO3 (top) and mass-flow uptake")

    # ET overview
    # ET overview with cumulative ET on secondary axis
    ax[2][1].plot(x, et0s, label="ET₀ PT (mm)")
    # Also compute PM ET0 for comparison (using simple wind/RH patterns)
    et0s_pm = []
    import math as _m

    for d in range(args.days):
        tmin, tmax, par = 10.0, 22.0, 12.0
        tmean = 0.5 * (tmin + tmax)
        et0_pm = etmod.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=par,
            method="penman-monteith",
            wind_m_s=2.0 + 1.0 * _m.sin(2 * _m.pi * d / 10.0),
            relative_humidity_pct=60.0 - 20.0 * _m.sin(2 * _m.pi * d / 15.0),
        )
        et0s_pm.append(et0_pm)
    ax[2][1].plot(x, et0s_pm, label="ET₀ PM (mm)")
    ax[2][1].plot(x, act_e, label="Actual Evap (mm)")
    ax[2][1].plot(x, act_t, label="Actual Transp (mm)")
    # Overlay VPD and stomatal factor for context
    vpd_series = [
        vpd_kpa(0.5 * (tmin + tmax), rh)
        for tmin, tmax, rh in zip(tmins, tmaxs, rhs, strict=False)
    ]
    stomatal = []
    for v in vpd_series:
        v_ex = max(0.0, v - etmod.params.vpd_ref_kpa)
        stomatal.append(max(0.2, 1.0 - etmod.params.vpd_sensitivity * v_ex))
    ax_et_aux = ax[2][1].twinx()
    ax_et_aux.plot(x, vpd_series, ":", color="#d62728", alpha=0.7, label="VPD (kPa)")
    ax_et_aux.plot(x, stomatal, "--", color="#2ca02c", alpha=0.7, label="Stomatal (-)")
    ax_et_aux.set_ylabel("kPa / -")
    # Optional stress highlighting via env var-like toggle (simple heuristic)
    # Shade where stomatal factor < 0.7
    for idx, sf in enumerate(stomatal, start=1):
        if sf < 0.7:
            ax[2][1].axvspan(
                idx - 0.5, idx + 0.5, color="#d62728", alpha=0.04, zorder=0
            )
    cum_et_total: List[float] = []
    _cum = 0.0
    for e_mm, t_mm in zip(act_e, act_t, strict=False):
        _cum += e_mm + t_mm
        cum_et_total.append(_cum)
    ax_et_cum = ax[2][1].twinx()
    ax_et_cum.plot(x, cum_et_total, "k--", label="Cumulative ET (mm)")
    ax_et_cum.set_ylabel("Cumulative ET (mm)")
    ax[2][1].set_title("Evapotranspiration")

    # Shared legend at bottom
    handles = []
    labels = []
    for a in [
        wx0,
        wx0b,
        wx1,
        ax_w,
        ax_w2,
        ax[0][1],
        ax[1][0],
        ax[1][1],
        ax[2][0],
        ax[2][1],
        ax_et_cum,
    ]:
        h, labels_part = a.get_legend_handles_labels()
        handles.extend(h)
        labels.extend(labels_part)
    # De-duplicate while preserving order
    seen = set()
    uniq_handles = []
    uniq_labels = []
    for handle, label in zip(handles, labels, strict=False):
        if label not in seen and label:
            seen.add(label)
            uniq_handles.append(handle)
            uniq_labels.append(label)
    ax_legend.legend(uniq_handles, uniq_labels, loc="center", ncol=5, frameon=False)

    # Shared x label
    for col in range(2):
        ax[2][col].set_xlabel("Day")

    # Stage transition gridlines across all panels and labels along x-axis
    transition_days: List[int] = []
    transition_labels: List[str] = []
    last = stage_series[0]
    transition_days.append(1)
    transition_labels.append(last.name)
    for day_idx, st in enumerate(stage_series, start=1):
        if st != last:
            transition_days.append(day_idx)
            transition_labels.append(st.name)
            last = st
    for a in [wx0, wx1, ax_w, ax[0][1], ax[1][0], ax[1][1], ax[2][0], ax[2][1]]:
        for d in transition_days:
            a.axvline(d, color="gray", linestyle=":", alpha=0.4, linewidth=0.8)
        a.grid(True, axis="x", which="both", linestyle=":", alpha=0.2)

    # Lightly shade phenology stages across all panels
    axes_to_shade = [wx0, wx1, ax_w, ax[0][1], ax[1][0], ax[1][1], ax[2][0], ax[2][1]]
    for i, label_name in enumerate(t_labels):
        start_day = t_days[i]
        end_day = t_days[i + 1] - 1
        color = stage_colors.get(label_name, plt.cm.tab10(i % 10))
        for a in axes_to_shade:
            a.axvspan(start_day, end_day, color=color, alpha=0.06, zorder=0)
    # Place stage labels below the bottom-left axis
    for d, name in zip(transition_days, transition_labels, strict=False):
        ax[2][0].annotate(
            name.replace("_", "\n"),
            xy=(d, -0.25),
            xycoords=("data", "axes fraction"),
            ha="center",
            va="top",
            fontsize=8,
        )

    fig.savefig(args.out, dpi=150, bbox_inches="tight", pad_inches=0.2)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
