from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.weather.utils import vpd_kpa, sanitize_weather_series
from agrogame.weather.constants import DEFAULT_ALBEDO
from scripts._weather_cli import add_weather_args, get_weather_series
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
from agrogame.plant.stress import compute_water_stress


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
    parser.add_argument(
        "--smooth-window",
        type=int,
        default=1,
        help="Moving-average window (days) for plotting",
    )
    parser.add_argument(
        "--stress-highlight",
        action="store_true",
        help="Shade days where stomatal factor < threshold (see --stress-threshold)",
    )
    parser.add_argument(
        "--stress-threshold",
        type=float,
        default=0.7,
        help="Threshold for highlighting stress (stomatal factor below this)",
    )
    add_weather_args(parser)
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
    et0s_pm: List[float] = []
    pot_e: List[float] = []
    pot_t: List[float] = []
    pot_e_pm: List[float] = []
    pot_t_pm: List[float] = []
    act_e: List[float] = []
    act_t: List[float] = []
    lais: List[float] = []
    # Weather diagnostics
    tmins: List[float] = []
    tmaxs: List[float] = []
    rhs: List[float] = []
    winds: List[float] = []
    rads: List[float] = []
    precs: List[float] = []
    vpds: List[float] = []
    stomatal_factors: List[float] = []

    # Cumulative trackers
    cum_et0 = 0.0
    cum_act_e = 0.0
    cum_act_t = 0.0

    import math

    # Optional automatic/file-based weather overrides pattern
    auto_series = get_weather_series(args, args.days)
    if auto_series is not None:
        auto_series = sanitize_weather_series(auto_series)

    # Respect available weather length to avoid trailing fallbacks
    total_days = args.days
    auto_series = auto_series
    if auto_series is not None:
        total_days = min(args.days, len(auto_series.records))

    for day in range(total_days):
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
        if auto_series and day < len(auto_series.records):
            rec = auto_series.records[day]
            tmin, tmax = rec.tmin_c, rec.tmax_c
            # Prefer provided net radiation; otherwise derive from shortwave
            if rec.net_radiation_mj_m2 is not None:
                rad = rec.net_radiation_mj_m2
            else:
                sw = rec.shortwave_mj_m2 or 0.0
                albedo = (
                    rec.albedo
                    if getattr(rec, "albedo", None) is not None
                    else DEFAULT_ALBEDO
                )
                rad = sw * max(0.0, 1.0 - albedo)
            rad = max(0.0, rad)
            wind = rec.wind_m_s or 2.0
            rh = rec.relative_humidity_pct or 60.0
        else:
            wind = 2.0 + 1.0 * math.sin(2 * math.pi * day / 10.0)
            rh = 60.0 - 20.0 * math.sin(2 * math.pi * day / 15.0)
        temp_mean = 0.5 * (tmin + tmax)
        vpd = vpd_kpa(temp_mean, rh)
        vpds.append(vpd)

        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=rain, evaporation_mm=evap0)
        )

        et0 = etmod.priestley_taylor(temp_mean_c=temp_mean, net_radiation_mj_m2=rad)
        et0_pm = etmod.et0(
            temp_mean_c=temp_mean,
            net_radiation_mj_m2=rad,
            method="penman-monteith",
            wind_m_s=wind,
            relative_humidity_pct=rh,
        )
        # Use VPD-aware partitioning for PT demand track
        comps = etmod.potential_components_with_vpd(
            et0_mm=et0, lai=canopy.state.lai, vpd_kpa=vpd_kpa(temp_mean, rh)
        )
        vpd_excess = max(0.0, vpd - etmod.params.vpd_ref_kpa)
        stomatal_factors.append(
            max(0.2, 1.0 - etmod.params.vpd_sensitivity * vpd_excess)
        )
        comps_pm = etmod.potential_components(et0_mm=et0_pm, lai=canopy.state.lai)

        # Actuals: use uniform root fractions across layers for demo
        n_layers = len(profile.layers)
        root_fracs = tuple([1.0 / n_layers] * n_layers)
        actual = etmod.actual_et(profile, wstate, water, comps, root_fracs)

        # Update canopy with a simple water stress proxy
        water_stress = compute_water_stress(
            actual.transpiration_mm, comps.potential_transp_mm
        )
        _ = canopy.daily_step(
            incident_par_mj_m2=rad,
            temp_factor=1.0,
            water_stress=water_stress,
            n_stress=1.0,
        )

        et0s.append(et0)
        et0s_pm.append(et0_pm)
        pot_e.append(comps.potential_evap_mm)
        pot_t.append(comps.potential_transp_mm)
        pot_e_pm.append(comps_pm.potential_evap_mm)
        pot_t_pm.append(comps_pm.potential_transp_mm)
        act_e.append(actual.evaporation_mm)
        act_t.append(actual.transpiration_mm)
        lais.append(canopy.state.lai)
        tmins.append(tmin)
        tmaxs.append(tmax)
        rhs.append(rh)
        winds.append(wind)
        rads.append(rad)
        if auto_series and day < len(auto_series.records):
            precs.append(auto_series.records[day].precip_mm or 0.0)
        else:
            precs.append(0.0)
        cum_et0 += et0
        cum_act_e += actual.evaporation_mm
        cum_act_t += actual.transpiration_mm

    # Optional smoothing
    def smooth(data: List[float]) -> List[float]:
        w = max(1, args.smooth_window)
        if w == 1:
            return data
        out: List[float] = []
        run = 0.0
        for i, v in enumerate(data):
            run += v
            if i >= w:
                run -= data[i - w]
            out.append(run / min(i + 1, w))
        return out

    # Sanitize weather series to avoid odd spikes/invalids
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

    # Recompute VPD and stomatal factor using sanitized weather to avoid outliers
    vpds = [vpd_kpa(0.5 * (tmins[i] + tmaxs[i]), rhs[i]) for i in range(len(tmins))]
    stomatal_factors = []
    for v in vpds:
        vpd_excess = max(0.0, v - etmod.params.vpd_ref_kpa)
        stomatal_factors.append(
            max(0.2, 1.0 - etmod.params.vpd_sensitivity * vpd_excess)
        )

    x = list(range(1, total_days + 1))
    plt.style.use("ggplot")
    fig = plt.figure(figsize=(12, 11), constrained_layout=True)
    gs = fig.add_gridspec(4, 2, height_ratios=[1.0, 1.0, 1.0, 0.8])
    ax_weather = fig.add_subplot(gs[0, :])
    ax_top = fig.add_subplot(gs[1, :])
    ax_evap = fig.add_subplot(gs[2, 0], sharex=ax_top)
    ax_transp = fig.add_subplot(gs[2, 1], sharex=ax_top)
    ax_lai = fig.add_subplot(gs[3, :], sharex=ax_top)

    # Panel 0: Weather drivers
    ax_weather.plot(x, smooth(tmins), color="#1f77b4", label="Tmin (°C)")
    ax_weather.plot(x, smooth(tmaxs), color="#ff7f0e", label="Tmax (°C)")
    ax_w2 = ax_weather.twinx()
    ax_w2.plot(x, smooth(rhs), color="#2ca02c", linestyle=":", label="RH (%)")
    ax_w2.plot(x, smooth(winds), color="#9467bd", linestyle="--", label="Wind (m/s)")
    ax_weather.set_title("Weather conditions")
    ax_weather.set_ylabel("°C")
    ax_w2.set_ylabel("% / m s⁻¹")
    # Radiation on separate axis to keep scale reasonable
    ax_w3 = ax_weather.twinx()
    ax_w3.spines.right.set_position(("axes", 1.08))
    ax_w3.plot(x, smooth(rads), color="#8c564b", alpha=0.6, label="Radiation (MJ m⁻²)")
    ax_weather.bar(x, precs, color="#1f77b4", alpha=0.15, label="Precip (mm)")
    # Build combined legend
    h1, l1 = ax_weather.get_legend_handles_labels()
    h2, l2 = ax_w2.get_legend_handles_labels()
    h3, l3 = ax_w3.get_legend_handles_labels()
    ax_weather.legend(h1 + h2 + h3, l1 + l2 + l3, ncol=3, loc="upper left")

    # Panel 1: ET0 PT vs PM
    ax_top.plot(x, smooth(et0s), label="ET0 PT (mm)")
    ax_top.plot(x, smooth(et0s_pm), label="ET0 PM (mm)")
    ax_top.set_title("ET0 (PT vs PM)")
    ax_top.set_ylabel("mm/day")
    ax_top.legend(loc="upper left")

    # Panel 2: Evaporation
    ax_evap.plot(x, smooth(pot_e), color="#999999", linestyle="-", label="Pot Evap PT")
    ax_evap.plot(
        x, smooth(pot_e_pm), color="#bbbbbb", linestyle="--", label="Pot Evap PM"
    )
    ax_evap.plot(x, smooth(act_e), color="C3", linewidth=2.0, label="Actual Evap")
    ax_evap.fill_between(x, smooth(act_e), smooth(pot_e), color="C3", alpha=0.15)
    ax_evap.set_title("Evaporation")
    ax_evap.set_ylabel("mm/day")
    ax_evap.legend(loc="upper left")

    # Panel 3: Transpiration
    ax_transp.plot(
        x, smooth(pot_t), color="#999999", linestyle="-", label="Pot Transp PT"
    )
    ax_transp.plot(
        x, smooth(pot_t_pm), color="#bbbbbb", linestyle="--", label="Pot Transp PM"
    )
    ax_transp.plot(x, smooth(act_t), color="C4", linewidth=2.0, label="Actual Transp")
    ax_transp.fill_between(x, smooth(act_t), smooth(pot_t), color="C4", alpha=0.15)
    ax_transp.set_title("Transpiration")
    ax_t2 = ax_transp.twinx()
    ax_t2.plot(x, vpds, color="#d62728", linestyle=":", alpha=0.7, label="VPD (kPa)")
    ax_t2.plot(
        x,
        stomatal_factors,
        color="#2ca02c",
        linestyle="--",
        alpha=0.7,
        label="Stomatal factor (-)",
    )
    ax_t2.set_ylabel("kPa / -")
    h1, l1 = ax_transp.get_legend_handles_labels()
    h2, l2 = ax_t2.get_legend_handles_labels()
    ax_transp.legend(h1 + h2, l1 + l2, loc="upper left")
    # Optional shading for stress periods
    if args.stress_highlight and stomatal_factors:
        thr = float(args.stress_threshold)
        for idx, sf in enumerate(stomatal_factors, start=1):
            if sf < thr:
                ax_transp.axvspan(
                    idx - 0.5, idx + 0.5, color="#d62728", alpha=0.06, zorder=0
                )

    # Bottom: LAI
    ax_lai.plot(x, smooth(lais), label="LAI")
    ax_lai.set_ylabel("LAI")
    ax_lai.set_xlabel("Day")
    ax_lai.legend(loc="upper left")

    fig.savefig(args.out, dpi=150)
    try:
        print(
            "Diagnostics:",
            f"VPD min/max={min(vpds):.3f}/{max(vpds):.3f}",
            f"Stomatal min/max={min(stomatal_factors):.3f}/{max(stomatal_factors):.3f}",
        )
    except Exception:
        pass
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
