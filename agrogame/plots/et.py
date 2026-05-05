from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.weather.utils import vpd_kpa, sanitize_weather_series
from agrogame.weather.constants import DEFAULT_ALBEDO
from agrogame.weather.cli import get_weather_series
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
from agrogame.plant.events import WaterStressComputed
from agrogame.plots.utils import moving_average, clamp_forward_fill, merge_legends


def _resolve_weather_pattern(
    day: int, pattern: str
) -> tuple[float, float, float, float, float]:
    """Return (tmin, tmax, rad, rain, evap0) for pattern-based weather."""
    if pattern == "seasonal":
        rad = 10.0 + 6.0 * math.sin(2 * math.pi * (day / 30.0))
        tavg = 16.0 + 6.0 * math.sin(2 * math.pi * (day / 30.0) + math.pi / 6.0)
        tmin, tmax = tavg - 5.0, tavg + 5.0
        rain = max(
            0.0,
            2.0 + 2.0 * math.sin(2 * math.pi * (day / 30.0) + math.pi / 3.0),
        )
        return tmin, tmax, rad, rain, 2.0
    if pattern == "storms":
        rain = 0.5 + (8.0 if (day % 7 == 0) else 0.0)
        return 10.0, 24.0, 12.0, rain, 2.0
    return 10.0, 24.0, 12.0, 3.0, 2.0


def _resolve_weather_for_day(
    day: int, pattern: str, auto_series: Any, total_days: int
) -> tuple[float, float, float, float, float, float, float]:
    """Return (tmin, tmax, rad, rain, evap0, wind, rh) for a day."""
    tmin, tmax, rad, rain, evap0 = _resolve_weather_pattern(day, pattern)
    if auto_series and day < len(auto_series.records):
        rec = auto_series.records[day]
        tmin, tmax = rec.tmin_c, rec.tmax_c
        if rec.net_radiation_mj_m2 is not None:
            rad = rec.net_radiation_mj_m2
        else:
            sw = rec.shortwave_mj_m2 or 0.0
            albedo = rec.albedo if rec.albedo is not None else DEFAULT_ALBEDO
            rad = sw * max(0.0, 1.0 - albedo)
        rad = max(0.0, rad)
        wind = rec.wind_m_s or 2.0
        rh = rec.relative_humidity_pct or 60.0
    else:
        wind = 2.0 + 1.0 * math.sin(2 * math.pi * day / 10.0)
        rh = 60.0 - 20.0 * math.sin(2 * math.pi * day / 15.0)
    return tmin, tmax, rad, rain, evap0, wind, rh


def _run_simulation(
    profile: str,
    days: int,
    pattern: str,
    weather_args: Any,
) -> tuple[dict[str, list[float]], int]:
    """Run simulation and return collected time series and total_days."""
    lib = load_soil_presets(Path("soils/presets.yaml"))
    soil_profile = lib.soils[profile]

    bus = EventBus()
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(soil_profile)
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

    data: dict[str, list[float]] = {
        k: []
        for k in [
            "et0s",
            "et0s_pm",
            "pot_e",
            "pot_t",
            "pot_e_pm",
            "pot_t_pm",
            "act_e",
            "act_t",
            "lais",
            "tmins",
            "tmaxs",
            "rhs",
            "winds",
            "rads",
            "precs",
            "vpds",
            "stomatal_factors",
            "water_stresses",
        ]
    }

    auto_series = get_weather_series(weather_args, days) if weather_args else None
    if auto_series is not None:
        auto_series = sanitize_weather_series(auto_series)
    total_days = min(days, len(auto_series.records)) if auto_series else days

    for day in range(total_days):
        tmin, tmax, rad, rain, evap0, wind, rh = _resolve_weather_for_day(
            day, pattern, auto_series, total_days
        )
        temp_mean = 0.5 * (tmin + tmax)
        vpd = vpd_kpa(temp_mean, rh)
        data["vpds"].append(vpd)

        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        _ = water.update_daily(
            soil_profile, wstate, DailyDrivers(rainfall_mm=rain, evaporation_mm=evap0)
        )

        et0 = etmod.priestley_taylor(temp_mean_c=temp_mean, net_radiation_mj_m2=rad)
        et0_pm = etmod.et0(
            temp_mean_c=temp_mean,
            net_radiation_mj_m2=rad,
            method="penman-monteith",
            wind_m_s=wind,
            relative_humidity_pct=rh,
        )
        comps = etmod.potential_components_with_vpd(
            et0_mm=et0, lai=canopy.state.lai, vpd_kpa=vpd_kpa(temp_mean, rh)
        )
        vpd_excess = max(0.0, vpd - etmod.params.vpd_ref_kpa)
        data["stomatal_factors"].append(
            max(0.2, 1.0 - etmod.params.vpd_sensitivity * vpd_excess)
        )
        comps_pm = etmod.potential_components(et0_mm=et0_pm, lai=canopy.state.lai)

        n_layers = len(soil_profile.layers)
        root_fracs = tuple([1.0 / n_layers] * n_layers)
        actual = etmod.actual_et(
            soil_profile,  # type: ignore[arg-type]
            wstate,  # type: ignore[arg-type]
            water,  # type: ignore[arg-type]
            comps,
            root_fracs,
        )

        ws = compute_water_stress(actual.transpiration_mm, comps.potential_transp_mm)
        bus.emit(
            WaterStressComputed(
                supply_mm=actual.transpiration_mm,
                demand_mm=comps.potential_transp_mm,
                stress=ws,
            )
        )
        _ = canopy.daily_step(
            incident_par_mj_m2=rad,
            temp_factor=1.0,
            water_stress=ws,
            n_stress=1.0,
        )
        data["water_stresses"].append(ws)

        data["et0s"].append(et0)
        data["et0s_pm"].append(et0_pm)
        data["pot_e"].append(comps.potential_evap_mm)
        data["pot_t"].append(comps.potential_transp_mm)
        data["pot_e_pm"].append(comps_pm.potential_evap_mm)
        data["pot_t_pm"].append(comps_pm.potential_transp_mm)
        data["act_e"].append(actual.evaporation_mm)
        data["act_t"].append(actual.transpiration_mm)
        data["lais"].append(canopy.state.lai)
        data["tmins"].append(tmin)
        data["tmaxs"].append(tmax)
        data["rhs"].append(rh)
        data["winds"].append(wind)
        data["rads"].append(rad)
        data["precs"].append(
            auto_series.records[day].precip_mm or 0.0 if auto_series else 0.0
        )

    # Store etmod params for post-processing
    data["_vpd_ref_kpa"] = [etmod.params.vpd_ref_kpa]
    data["_vpd_sensitivity"] = [etmod.params.vpd_sensitivity]

    return data, total_days


def _postprocess_weather(
    data: dict[str, list[float]],
) -> None:
    """Clamp/fill weather and recompute VPD/stomatal from cleaned data in-place."""
    data["tmins"] = clamp_forward_fill(data["tmins"], -60.0, 60.0)
    data["tmaxs"] = clamp_forward_fill(data["tmaxs"], -60.0, 60.0)
    data["rhs"] = clamp_forward_fill(data["rhs"], 0.0, 100.0)
    data["winds"] = clamp_forward_fill(data["winds"], 0.0, 60.0)

    vpd_ref = data["_vpd_ref_kpa"][0]
    vpd_sens = data["_vpd_sensitivity"][0]

    data["vpds"] = [
        vpd_kpa(0.5 * (data["tmins"][i] + data["tmaxs"][i]), data["rhs"][i])
        for i in range(len(data["tmins"]))
    ]
    data["stomatal_factors"] = []
    for v in data["vpds"]:
        vpd_excess = max(0.0, v - vpd_ref)
        data["stomatal_factors"].append(max(0.2, 1.0 - vpd_sens * vpd_excess))


def _render_plots(
    data: dict[str, list[float]],
    total_days: int,
    out: Path,
    smooth_window: int,
    stress_highlight: bool,
    stress_threshold: float,
) -> None:
    """Create the figure and render all subplots."""

    def smooth(vals: list[float]) -> list[float]:
        return moving_average(vals, smooth_window)

    x = list(range(1, total_days + 1))
    plt.style.use("ggplot")
    fig = plt.figure(figsize=(12, 11), constrained_layout=True)
    gs = fig.add_gridspec(4, 2, height_ratios=[1.0, 1.0, 1.0, 0.8])
    ax_weather = fig.add_subplot(gs[0, :])
    ax_top = fig.add_subplot(gs[1, :])
    ax_evap = fig.add_subplot(gs[2, 0], sharex=ax_top)
    ax_transp = fig.add_subplot(gs[2, 1], sharex=ax_top)
    ax_lai = fig.add_subplot(gs[3, :], sharex=ax_top)

    _plot_weather_panel(ax_weather, x, data, smooth)
    _plot_et0_panel(ax_top, x, data, smooth)
    _plot_evap_panel(ax_evap, x, data, smooth)
    _plot_transp_panel(ax_transp, x, data, smooth, stress_highlight, stress_threshold)

    ax_lai.plot(x, smooth(data["lais"]), label="LAI")
    ax_lai.set_ylabel("LAI")
    ax_lai.set_xlabel("Day")
    ax_lai.legend(loc="upper left")

    fig.savefig(out, dpi=150)
    print("Saved", out)


def _plot_weather_panel(ax_weather: Any, x: list, data: dict, smooth: Any) -> None:
    ax_weather.plot(x, smooth(data["tmins"]), color="#1f77b4", label="Tmin (°C)")
    ax_weather.plot(x, smooth(data["tmaxs"]), color="#ff7f0e", label="Tmax (°C)")
    ax_w2 = ax_weather.twinx()
    ax_w2.plot(x, smooth(data["rhs"]), color="#2ca02c", linestyle=":", label="RH (%)")
    ax_w2.plot(
        x, smooth(data["winds"]), color="#9467bd", linestyle="--", label="Wind (m/s)"
    )
    ax_weather.set_title("Weather conditions")
    ax_weather.set_ylabel("°C")
    ax_w2.set_ylabel("% / m s⁻¹")
    ax_w3 = ax_weather.twinx()
    ax_w3.spines.right.set_position(("axes", 1.08))
    ax_w3.plot(
        x, smooth(data["rads"]), color="#8c564b", alpha=0.6, label="Radiation (MJ m⁻²)"
    )
    ax_weather.bar(x, data["precs"], color="#1f77b4", alpha=0.15, label="Precip (mm)")
    handles, labels = merge_legends(ax_weather, ax_w2, ax_w3)
    ax_weather.legend(handles, labels, ncol=3, loc="upper left")


def _plot_et0_panel(ax_top: Any, x: list, data: dict, smooth: Any) -> None:
    ax_top.plot(x, smooth(data["et0s"]), label="ET0 PT (mm)")
    ax_top.plot(x, smooth(data["et0s_pm"]), label="ET0 PM (mm)")
    ax_top.set_title("ET0 (PT vs PM)")
    ax_top.set_ylabel("mm/day")
    ax_top.legend(loc="upper left")


def _plot_evap_panel(ax_evap: Any, x: list, data: dict, smooth: Any) -> None:
    ax_evap.plot(
        x, smooth(data["pot_e"]), color="#999999", linestyle="-", label="Pot Evap PT"
    )
    ax_evap.plot(
        x,
        smooth(data["pot_e_pm"]),
        color="#bbbbbb",
        linestyle="--",
        label="Pot Evap PM",
    )
    ax_evap.plot(
        x, smooth(data["act_e"]), color="C3", linewidth=2.0, label="Actual Evap"
    )
    ax_evap.fill_between(
        x, smooth(data["act_e"]), smooth(data["pot_e"]), color="C3", alpha=0.15
    )
    ax_evap.set_title("Evaporation")
    ax_evap.set_ylabel("mm/day")
    ax_evap.legend(loc="upper left")


def _plot_transp_panel(
    ax_transp: Any,
    x: list,
    data: dict,
    smooth: Any,
    stress_highlight: bool,
    stress_threshold: float,
) -> None:
    ax_transp.plot(
        x, smooth(data["pot_t"]), color="#999999", linestyle="-", label="Pot Transp PT"
    )
    ax_transp.plot(
        x,
        smooth(data["pot_t_pm"]),
        color="#bbbbbb",
        linestyle="--",
        label="Pot Transp PM",
    )
    ax_transp.plot(
        x, smooth(data["act_t"]), color="C4", linewidth=2.0, label="Actual Transp"
    )
    ax_transp.fill_between(
        x, smooth(data["act_t"]), smooth(data["pot_t"]), color="C4", alpha=0.15
    )
    ax_transp.set_title("Transpiration")
    ax_t2 = ax_transp.twinx()
    ax_t2.plot(
        x, data["vpds"], color="#d62728", linestyle=":", alpha=0.7, label="VPD (kPa)"
    )
    ax_t2.plot(
        x,
        data["stomatal_factors"],
        color="#2ca02c",
        linestyle="--",
        alpha=0.7,
        label="Stomatal factor (-)",
    )
    ax_t2.set_ylabel("kPa / -")
    ax_t3 = ax_transp.twinx()
    ax_t3.spines.right.set_position(("axes", 1.08))
    ax_t3.plot(
        x,
        data["water_stresses"],
        color="#17becf",
        alpha=0.8,
        label="Water stress (-)",
    )
    ax_t3.set_ylim(0.0, 1.05)
    handles, labels = merge_legends(ax_transp, ax_t2, ax_t3)
    ax_transp.legend(handles, labels, loc="upper left")
    if stress_highlight and data["stomatal_factors"]:
        thr = float(stress_threshold)
        for idx, sf in enumerate(data["stomatal_factors"], start=1):
            if sf < thr:
                ax_transp.axvspan(
                    idx - 0.5, idx + 0.5, color="#d62728", alpha=0.06, zorder=0
                )


def plot_et_timeseries(
    profile: str,
    days: int,
    out: Path,
    pattern: str = "constant",
    smooth_window: int = 1,
    stress_highlight: bool = False,
    stress_threshold: float = 0.7,
    weather_args: Any = None,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    data, total_days = _run_simulation(profile, days, pattern, weather_args)
    _postprocess_weather(data)
    _render_plots(
        data, total_days, out, smooth_window, stress_highlight, stress_threshold
    )
