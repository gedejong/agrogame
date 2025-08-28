from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.weather.constants import DEFAULT_ALBEDO
from agrogame.weather.utils import vpd_kpa
from scripts._weather_cli import add_weather_args, get_weather_series
from agrogame.soil.canopy.interception import InterceptionState


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot canopy rainfall interception in isolation"
    )
    add_weather_args(parser)
    parser.add_argument("--days", type=int, default=60)
    parser.add_argument("--lai", type=float, default=3.0, help="Constant LAI")
    parser.add_argument(
        "--cap-per-lai",
        type=float,
        default=0.2,
        help="Interception capacity coefficient (mm per unit LAI)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("out/interception_isolation.png")
    )
    args = parser.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Weather
    auto = get_weather_series(args, args.days)
    total_days = args.days if auto is None else min(args.days, len(auto.records))

    # Series
    rain: List[float] = []
    rad: List[float] = []
    tmins: List[float] = []
    tmaxs: List[float] = []
    rhs: List[float] = []
    vpds: List[float] = []
    intercepted: List[float] = []
    throughfall: List[float] = []
    store: List[float] = []
    canopy_evap: List[float] = []
    evap_left_for_soil: List[float] = []

    istate = InterceptionState(capacity_coef_mm_per_lai=args.cap_per_lai)
    et = Evapotranspiration(EtParams())

    for d in range(total_days):
        rec = auto.records[d] if auto else None
        if rec is not None:
            tmin, tmax = rec.tmin_c, rec.tmax_c
            r = rec.precip_mm or 0.0
            if rec.net_radiation_mj_m2 is not None:
                rn = rec.net_radiation_mj_m2
            else:
                sw = rec.shortwave_mj_m2 or 0.0
                alb = (
                    rec.albedo
                    if getattr(rec, "albedo", None) is not None
                    else DEFAULT_ALBEDO
                )
                rn = sw * max(0.0, 1.0 - alb)
            rn = max(0.0, rn)
            rh = rec.relative_humidity_pct or 60.0
        else:
            # Fallback synthetic
            tmin, tmax, rn, r, rh = 10.0, 24.0, 12.0, 3.0, 60.0

        tmean = 0.5 * (tmin + tmax)
        vpd = vpd_kpa(tmean, rh)
        vpds.append(vpd)

        # Interception
        take, tf = istate.intercept(args.lai, r)
        intercepted.append(take)
        throughfall.append(tf)
        store.append(istate.store_mm)

        # Potential evaporation for the day (PT-based partitioning)
        et0 = et.priestley_taylor(tmean, rn)
        comps = et.potential_components_with_vpd(et0, args.lai, vpd)
        ce = istate.evaporate(comps.potential_evap_mm)
        canopy_evap.append(ce)
        evap_left_for_soil.append(max(0.0, comps.potential_evap_mm - ce))

        rain.append(r)
        rad.append(rn)
        tmins.append(tmin)
        tmaxs.append(tmax)
        rhs.append(rh)

    # Sanitize weather for display
    tmins = _ffill_clamp(tmins, -60.0, 60.0)
    tmaxs = _ffill_clamp(tmaxs, -60.0, 60.0)
    rhs = _ffill_clamp(rhs, 0.0, 100.0)

    x = list(range(1, total_days + 1))
    plt.style.use("ggplot")
    fig = plt.figure(figsize=(12, 9), constrained_layout=True)
    gs = fig.add_gridspec(4, 1, height_ratios=[1.0, 1.0, 1.0, 0.8])
    ax0 = fig.add_subplot(gs[0, 0])
    ax1 = fig.add_subplot(gs[1, 0], sharex=ax0)
    ax2 = fig.add_subplot(gs[2, 0], sharex=ax0)
    ax3 = fig.add_subplot(gs[3, 0], sharex=ax0)

    # Weather quick view
    ax0.plot(x, tmins, label="Tmin (°C)")
    ax0.plot(x, tmaxs, label="Tmax (°C)")
    ax0b = ax0.twinx()
    ax0b.bar(x, rain, color="#1f77b4", alpha=0.15, label="Precip (mm)")
    ax0b.plot(x, rad, ":", color="#8c564b", alpha=0.6, label="Rn (MJ m⁻²)")
    ax0.set_title("Weather & inputs")
    h1, l1 = ax0.get_legend_handles_labels()
    h2, l2 = ax0b.get_legend_handles_labels()
    ax0.legend(h1 + h2, l1 + l2, ncol=3, loc="upper left")

    # Interception vs throughfall
    ax1.bar(x, throughfall, color="#9ecae1", label="Throughfall (mm)")
    ax1.bar(
        x,
        intercepted,
        bottom=throughfall,
        color="#3182bd",
        alpha=0.7,
        label="Intercepted (mm)",
    )
    ax1.set_title("Rain partitioning")
    ax1.legend(loc="upper left")

    # Canopy store
    ax2.plot(x, store, color="#9467bd", label="Canopy store (mm)")
    ax2.set_title("Canopy water store")
    ax2.legend(loc="upper left")

    # Evaporation from canopy and residual for soil
    ax3.plot(x, canopy_evap, color="#2ca02c", label="Canopy evaporation (mm)")
    ax3.plot(
        x,
        evap_left_for_soil,
        color="#d62728",
        linestyle="--",
        label="Residual potential evap for soil (mm)",
    )
    ax3b = ax3.twinx()
    ax3b.plot(x, vpds, ":", color="#ff7f0e", alpha=0.7, label="VPD (kPa)")
    h3, l3 = ax3.get_legend_handles_labels()
    h3b, l3b = ax3b.get_legend_handles_labels()
    ax3.legend(h3 + h3b, l3 + l3b, ncol=2, loc="upper left")
    ax3.set_title("Evaporation & VPD context")
    ax3.set_xlabel("Day")

    fig.savefig(args.out, dpi=150)
    print(f"Saved {args.out}")


if __name__ == "__main__":
    main()
