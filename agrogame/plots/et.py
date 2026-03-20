from __future__ import annotations

from pathlib import Path
from typing import Any, List

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

    et0s: List[float] = []
    et0s_pm: List[float] = []
    pot_e: List[float] = []
    pot_t: List[float] = []
    pot_e_pm: List[float] = []
    pot_t_pm: List[float] = []
    act_e: List[float] = []
    act_t: List[float] = []
    lais: List[float] = []
    tmins: List[float] = []
    tmaxs: List[float] = []
    rhs: List[float] = []
    winds: List[float] = []
    rads: List[float] = []
    precs: List[float] = []
    vpds: List[float] = []
    stomatal_factors: List[float] = []
    water_stresses: List[float] = []

    import math

    auto_series = get_weather_series(weather_args, days) if weather_args else None
    if auto_series is not None:
        auto_series = sanitize_weather_series(auto_series)
    total_days = min(days, len(auto_series.records)) if auto_series else days

    for day in range(total_days):
        if pattern == "seasonal":
            rad = 10.0 + 6.0 * math.sin(2 * math.pi * (day / 30.0))
            tavg = 16.0 + 6.0 * math.sin(2 * math.pi * (day / 30.0) + math.pi / 6.0)
            tmin, tmax = tavg - 5.0, tavg + 5.0
            rain = max(
                0.0,
                2.0 + 2.0 * math.sin(2 * math.pi * (day / 30.0) + math.pi / 3.0),
            )
            evap0 = 2.0
        elif pattern == "storms":
            rad = 12.0
            tmin, tmax = 10.0, 24.0
            rain = 0.5 + (8.0 if (day % 7 == 0) else 0.0)
            evap0 = 2.0
        else:
            tmin, tmax = 10.0, 24.0
            rad = 12.0
            rain, evap0 = 3.0, 2.0
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
        temp_mean = 0.5 * (tmin + tmax)
        vpd = vpd_kpa(temp_mean, rh)
        vpds.append(vpd)

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
        stomatal_factors.append(
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

        water_stress = compute_water_stress(
            actual.transpiration_mm, comps.potential_transp_mm
        )
        bus.emit(
            WaterStressComputed(
                supply_mm=actual.transpiration_mm,
                demand_mm=comps.potential_transp_mm,
                stress=water_stress,
            )
        )
        _ = canopy.daily_step(
            incident_par_mj_m2=rad,
            temp_factor=1.0,
            water_stress=water_stress,
            n_stress=1.0,
        )
        water_stresses.append(water_stress)

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
        precs.append(auto_series.records[day].precip_mm or 0.0 if auto_series else 0.0)

    def smooth(data: List[float]) -> List[float]:
        return moving_average(data, smooth_window)

    tmins = clamp_forward_fill(tmins, -60.0, 60.0)
    tmaxs = clamp_forward_fill(tmaxs, -60.0, 60.0)
    rhs = clamp_forward_fill(rhs, 0.0, 100.0)
    winds = clamp_forward_fill(winds, 0.0, 60.0)

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

    ax_weather.plot(x, smooth(tmins), color="#1f77b4", label="Tmin (°C)")
    ax_weather.plot(x, smooth(tmaxs), color="#ff7f0e", label="Tmax (°C)")
    ax_w2 = ax_weather.twinx()
    ax_w2.plot(x, smooth(rhs), color="#2ca02c", linestyle=":", label="RH (%)")
    ax_w2.plot(x, smooth(winds), color="#9467bd", linestyle="--", label="Wind (m/s)")
    ax_weather.set_title("Weather conditions")
    ax_weather.set_ylabel("°C")
    ax_w2.set_ylabel("% / m s⁻¹")
    ax_w3 = ax_weather.twinx()
    ax_w3.spines.right.set_position(("axes", 1.08))
    ax_w3.plot(x, smooth(rads), color="#8c564b", alpha=0.6, label="Radiation (MJ m⁻²)")
    ax_weather.bar(x, precs, color="#1f77b4", alpha=0.15, label="Precip (mm)")
    handles, labels = merge_legends(ax_weather, ax_w2, ax_w3)
    ax_weather.legend(handles, labels, ncol=3, loc="upper left")

    ax_top.plot(x, smooth(et0s), label="ET0 PT (mm)")
    ax_top.plot(x, smooth(et0s_pm), label="ET0 PM (mm)")
    ax_top.set_title("ET0 (PT vs PM)")
    ax_top.set_ylabel("mm/day")
    ax_top.legend(loc="upper left")

    ax_evap.plot(x, smooth(pot_e), color="#999999", linestyle="-", label="Pot Evap PT")
    ax_evap.plot(
        x, smooth(pot_e_pm), color="#bbbbbb", linestyle="--", label="Pot Evap PM"
    )
    ax_evap.plot(x, smooth(act_e), color="C3", linewidth=2.0, label="Actual Evap")
    ax_evap.fill_between(x, smooth(act_e), smooth(pot_e), color="C3", alpha=0.15)
    ax_evap.set_title("Evaporation")
    ax_evap.set_ylabel("mm/day")
    ax_evap.legend(loc="upper left")

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
    ax_t3 = ax_transp.twinx()
    ax_t3.spines.right.set_position(("axes", 1.08))
    ax_t3.plot(x, water_stresses, color="#17becf", alpha=0.8, label="Water stress (-)")
    ax_t3.set_ylim(0.0, 1.05)
    handles, labels = merge_legends(ax_transp, ax_t2, ax_t3)
    ax_transp.legend(handles, labels, loc="upper left")
    if stress_highlight and stomatal_factors:
        thr = float(stress_threshold)
        for idx, sf in enumerate(stomatal_factors, start=1):
            if sf < thr:
                ax_transp.axvspan(
                    idx - 0.5, idx + 0.5, color="#d62728", alpha=0.06, zorder=0
                )

    ax_lai.plot(x, smooth(lais), label="LAI")
    ax_lai.set_ylabel("LAI")
    ax_lai.set_xlabel("Day")
    ax_lai.legend(loc="upper left")

    fig.savefig(out, dpi=150)
    print("Saved", out)
