from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List
from io import StringIO

import pandas as pd

from agrogame.sim.engine import SimulationEngine
from agrogame.soil.loader import load_soil_presets
from agrogame.events.recorder import EventRecorder
from agrogame.soil.water.events import EvaporationTaken, TranspirationByLayer
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.weather import load_weather as _load_weather


def run_engine(
    profile: str,
    weather_file: Path,
    days: int,
    irrig: List[str] | None,
    out_dir: Path,
    fert_an: List[str] | None = None,
    fert_urea: List[str] | None = None,
    lime: List[str] | None = None,
    harvest: int | None = None,
) -> Dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    eng = SimulationEngine(soil_lib.soils[profile], weather_file)
    et = Evapotranspiration(EtParams())
    weather = _load_weather(weather_file)

    # Subscribe event recorder for analysis
    # Recorder subscribes to BaseEvent via orchestrator bus
    rec = EventRecorder(eng.orchestrator.event_bus)

    # Schedule irrigation flags like "day,mm"
    for spec in irrig or []:
        day_s, mm_s = spec.split(",")
        eng.schedule_irrigation(int(day_s), float(mm_s))
    # Other management
    for spec in fert_an or []:
        d, kg, layer = spec.split(",")
        eng.schedule_fertilizer_an(int(d), float(kg), int(layer))
    for spec in fert_urea or []:
        d, kg, layer = spec.split(",")
        eng.schedule_fertilizer_urea(int(d), float(kg), int(layer))
    for spec in lime or []:
        d, kg, layer = spec.split(",")
        eng.schedule_lime(int(d), float(kg), int(layer))
    if isinstance(harvest, int) and harvest >= 0:
        eng.schedule_harvest(int(harvest))

    # Daily aggregations
    evap_series: List[float] = []
    transp_series: List[float] = []
    lai_series: List[float] = []
    biomass_series: List[float] = []
    nmin_series: List[float] = []
    day_labels: List[Any] = []
    et0_series: List[float] = []
    water_stress_series: List[float] = []

    # In-memory day counters via event subscriptions
    daily = {"evap": 0.0, "transp": 0.0}

    def _on_evap(ev: EvaporationTaken) -> None:
        daily["evap"] += float(ev.amount_mm)

    def _on_transp(ev: TranspirationByLayer) -> None:
        total = float(getattr(ev, "total_mm", sum(ev.amounts_mm)))
        daily["transp"] += total

    eng.orchestrator.event_bus.subscribe(EvaporationTaken, _on_evap)
    eng.orchestrator.event_bus.subscribe(TranspirationByLayer, _on_transp)

    # Run for requested days (stop early if maturity)
    for _ in range(days):
        # Reset daily counters
        daily["evap"] = 0.0
        daily["transp"] = 0.0
        rec.set_day(int(eng.current_day))
        eng.advance_day()
        if eng._is_done():  # type: ignore[attr-defined]
            break
        # Collect daily series after step
        day_labels.append(int(eng.current_day))
        evap_series.append(daily["evap"])
        transp_series.append(daily["transp"])
        lai_val = float(getattr(eng.orchestrator.canopy.state, "lai", 0.0))
        lai_series.append(lai_val)
        biomass_series.append(
            float(getattr(eng.orchestrator.canopy.state, "biomass_g_m2", 0.0))
        )
        nmin_series.append(
            float(sum(eng.orchestrator.n_state.no3) + sum(eng.orchestrator.n_state.nh4))
        )
        # ET0 and water stress overlay using weather and ET partitioning
        idx = max(0, min(len(weather.records) - 1, eng.current_day - 1))
        recw = weather.records[idx]
        tmean = 0.5 * (recw.tmin_c + recw.tmax_c)
        rn = recw.net_radiation_mj_m2 or recw.shortwave_mj_m2 or 12.0
        et0_val = et.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="priestley_taylor",
        )
        et0_series.append(et0_val)
        pot = et.potential_components(et0_mm=et0_val, lai=lai_val)
        demand = max(1e-6, pot.potential_transp_mm)
        water_stress_series.append(max(0.05, min(1.0, daily["transp"] / demand)))

    # Convert events to DataFrame
    rows: List[Dict[str, Any]] = []
    for ev in rec.events:
        # Normalize day index for grouping; keep sim_date separately if present
        sim_date = ev.data.get("sim_date")
        row = {
            "day_idx": ev.day_index,
            "date": sim_date,
            "event": ev.event_type,
            "module": ev.module_name,
            **{k: v for k, v in ev.data.items() if k not in ("timestamp",)},
        }
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "events.csv", index=False)

    # Simple aggregations: counts per day and per module
    by_day = df.groupby("day_idx").size().rename("events").reset_index()
    by_day.to_csv(out_dir / "events_by_day.csv", index=False)
    by_mod = df.groupby(["day_idx", "module"]).size().rename("events").reset_index()
    by_mod.to_csv(out_dir / "events_by_module.csv", index=False)

    # Timeseries CSV
    ts = pd.DataFrame(
        {
            "day": day_labels,
            "evap_mm": evap_series,
            "transp_mm": transp_series,
            "lai": lai_series,
            "biomass_g_m2": biomass_series,
            "nmin_kgha": nmin_series,
            "et0_mm": et0_series,
            "water_stress": water_stress_series,
        }
    )
    ts.to_csv(out_dir / "timeseries.csv", index=False)

    # Plotting (saved as PNG); imports local to keep optional deps
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(2, 2, figsize=(12, 8))
        # Events by day
        ax[0][0].plot(by_day["day_idx"], by_day["events"], label="events/day")
        ax[0][0].set_title("Event volume by day")
        ax[0][0].set_xlabel("Day")
        ax[0][0].set_ylabel("Events")
        # ET components + ET0 overlay and stress shading
        ax[0][1].plot(ts["day"], ts["evap_mm"], label="evap")
        ax[0][1].plot(ts["day"], ts["transp_mm"], label="transp")
        ax[0][1].plot(ts["day"], ts["et0_mm"], label="ET0", linestyle="--")
        stress_mask = (ts["water_stress"] < 0.99).astype(int)
        if stress_mask.any():
            ax_s = ax[0][1].twinx()
            ax_s.fill_between(ts["day"], 0, stress_mask, color="red", alpha=0.1)
            ax_s.set_yticks([])

        # Annotate management days (shift +1 to align with post-step day index)
        def _parse_days(specs: List[str] | None) -> list[int]:
            days_list: list[int] = []
            for s in specs or []:
                d = int(s.split(",")[0]) + 1
                days_list.append(d)
            return days_list

        irr_days = _parse_days(irrig)
        an_days = _parse_days(fert_an)
        urea_days = _parse_days(fert_urea)
        lime_days = _parse_days(lime)
        harvest_days = [int(harvest) + 1] if isinstance(harvest, int) else []

        for d in irr_days:
            ax[0][1].axvline(d, color="tab:blue", alpha=0.25, linestyle=":")
        for d in an_days:
            ax[0][1].axvline(d, color="saddlebrown", alpha=0.25, linestyle=":")
        for d in urea_days:
            ax[0][1].axvline(d, color="purple", alpha=0.25, linestyle=":")
        for d in lime_days:
            ax[0][1].axvline(d, color="gray", alpha=0.25, linestyle=":")
        for d in harvest_days:
            ax[0][1].axvline(d, color="black", alpha=0.35, linestyle="--")
        ax[0][1].set_title("ET components and ET0 (stress shaded)")
        ax[0][1].legend()
        # Canopy/biomass
        ax[1][0].plot(ts["day"], ts["lai"], label="LAI")
        ax[1][0].set_ylabel("LAI")
        ax_t = ax[1][0].twinx()
        ax_t.plot(ts["day"], ts["biomass_g_m2"], color="tab:orange", label="Biomass")
        ax[1][0].set_title("Canopy and Biomass")
        # Mineral N
        ax[1][1].plot(ts["day"], ts["nmin_kgha"], color="tab:green")
        ax[1][1].set_title("Mineral N (kg/ha)")
        # Top modules last day
        tail = by_mod[by_mod["day_idx"] == by_mod["day_idx"].max()]
        top = tail.sort_values("events", ascending=False).head(10)
        # Put top modules as inset bar on ET plot area
        from mpl_toolkits.axes_grid1.inset_locator import inset_axes

        inset = inset_axes(ax[0][1], width="40%", height="60%", loc="upper right")
        inset.barh(top["module"], top["events"])
        inset.set_title("Top modules (last day)")
        plt.tight_layout()
        fig.savefig(out_dir / "events_summary.png", dpi=150)

        # Correlation heatmap across key timeseries

        corr = ts[
            [
                "evap_mm",
                "transp_mm",
                "et0_mm",
                "lai",
                "biomass_g_m2",
                "nmin_kgha",
                "water_stress",
            ]
        ].corr()
        fig2, ax2 = plt.subplots(figsize=(6, 5))
        cax = ax2.imshow(corr.values, cmap="viridis", vmin=-1, vmax=1)
        ax2.set_xticks(range(len(corr.columns)))
        ax2.set_xticklabels(corr.columns, rotation=45, ha="right")
        ax2.set_yticks(range(len(corr.index)))
        ax2.set_yticklabels(corr.index)
        for i in range(len(corr.index)):
            for j in range(len(corr.columns)):
                ax2.text(
                    j,
                    i,
                    f"{corr.values[i,j]:.2f}",
                    va="center",
                    ha="center",
                    color="white",
                )
        fig2.colorbar(cax, ax=ax2, fraction=0.046, pad=0.04)
        ax2.set_title("Timeseries correlations")
        fig2.tight_layout()
        fig2.savefig(out_dir / "timeseries_correlations.png", dpi=150)
    except ImportError:
        # matplotlib not installed; skip plotting
        pass

    return {
        "rows": len(df),
        "days": int(by_day["day_idx"].nunique() if not by_day.empty else 0),
    }


def main() -> None:
    p = argparse.ArgumentParser(description="Run SimulationEngine and analyze outputs")
    p.add_argument("--profile", default="loam_temperate")
    p.add_argument("--weather-file", type=Path, default=Path("data/weather/sample.csv"))
    p.add_argument("--days", type=int, default=120)
    p.add_argument(
        "--irrigate",
        action="append",
        help="Irrigation spec as 'day,mm' (repeatable)",
    )
    p.add_argument(
        "--fert-an",
        action="append",
        help="Ammonium nitrate as 'day,kg_ha,layer' (repeatable)",
    )
    p.add_argument(
        "--fert-urea",
        action="append",
        help="Urea as 'day,kg_ha,layer' (repeatable)",
    )
    p.add_argument(
        "--lime",
        action="append",
        help="Lime as 'day,kg_ha,layer' (repeatable)",
    )
    p.add_argument(
        "--harvest", type=int, default=-1, help="Harvest day index (optional)"
    )
    p.add_argument("--out", type=Path, default=Path("out/engine_analysis"))
    args = p.parse_args()

    # Run full analysis (events, timeseries, plots)
    _ = run_engine(
        args.profile,
        args.weather_file,
        args.days,
        args.irrigate,
        args.out,
        fert_an=args.fert_an,
        fert_urea=args.fert_urea,
        lime=args.lime,
        harvest=args.harvest if args.harvest >= 0 else None,
    )

    # Write markdown report
    report = args.out / "report.md"
    with report.open("w") as f:
        f.write("# Season report\n\n")
        f.write(f"Profile: {args.profile}  ")
        f.write(f"Weather: {args.weather_file}\n\n")
        f.write("## Management\n")
        irr_str = ", ".join(args.irrigate or []) if args.irrigate else "none"
        f.write(f"Irrigation: {irr_str}\n\n")
        f.write(f"AN: {', '.join(args.fert_an or []) if args.fert_an else 'none'}  ")
        f.write(
            f"Urea: {', '.join(args.fert_urea or []) if args.fert_urea else 'none'}  "
        )
        f.write(f"Lime: {', '.join(args.lime or []) if args.lime else 'none'}  ")
        f.write(f"Harvest: {args.harvest if args.harvest>=0 else 'none'}\n\n")
        f.write("## Summary statistics\n")
        ts = pd.read_csv(args.out / "timeseries.csv")
        desc = ts.describe()
        try:
            f.write(desc.to_markdown(index=True))
        except Exception:
            buf = StringIO()
            desc.to_csv(buf)
            f.write("\n```csv\n")
            f.write(buf.getvalue())
            f.write("```\n")
        f.write("\n\n## Figures\n")
        f.write("![](events_summary.png)\n\n")
        f.write("![](timeseries_correlations.png)\n")

    print(f"Wrote analysis to {args.out} (report.md, CSVs, PNGs)")


if __name__ == "__main__":
    main()
