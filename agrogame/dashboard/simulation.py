"""Thin orchestration layer for the Streamlit dashboard.

All engine-internal types and event subscribers live in
``agrogame.api.dashboard_facade`` — see ADR-011. This module is the
dashboard-side glue that binds user-supplied schedules (irrigation,
fertilizer ops, weather file path) to the façade's
:class:`DashboardSimulationRun`.

Pre-#309 this file ran the orchestrator directly and held the six
event subscribers itself; that work has been lifted into the façade so
the dashboard never names engine-internal types.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agrogame.api.dashboard_facade import (
    DashboardSimulationRun,
    SoilProfile,
    apply_fertilizers,
    extend_weather_records,
    load_soil_profile,
    load_weather_records,
    make_drivers,
)


def _run_simulation(
    days: int,
    weather_file: Path,
    irrigation_schedule: list[tuple[int, float]] | None = None,
    fertilizer_schedule: list[tuple[int, float]] | None = None,
    *,
    fertilizer_ops: list[tuple[int, float, str, int]] | None = None,
) -> tuple[dict[str, Any], SoilProfile]:
    """Drive a multi-day simulation through the façade and return the history."""
    profile = load_soil_profile()
    run = DashboardSimulationRun(profile)
    records = extend_weather_records(load_weather_records(weather_file), days)

    irrig_map: Mapping[int, float] = dict(irrigation_schedule or [])
    fert_map: Mapping[int, float] = dict(fertilizer_schedule or [])
    fert_ops = list(fertilizer_ops or [])

    for i in range(min(days, len(records))):
        rec = records[i]
        rain = rec.precip_mm or 0.0
        irrigation = irrig_map.get(i, 0.0)

        apply_fertilizers(run.n_cycle, i, fert_ops, fert_map)

        et0, et0_pt, par, _rn, tmean, vpd = run.compute_reference_et(rec)
        run.history["et0_mm"].append(et0)
        run.history["et0_pt_mm"].append(et0_pt)

        run.reset_daily_counters()
        run.step_day(
            make_drivers(rain + irrigation),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
        )

        water_stress, stomatal = run.calc_stress(
            vpd=vpd,
            lai=run.lai,
            transp_mm=run.agg.transp_mm,
            et0_mm=et0,
        )
        run.append_day_summary(
            et0=et0, water_stress=water_stress, vpd=vpd, stomatal=stomatal
        )
        run.append_micro_activity(day_index=i)
        run.history["day"].append(rec.day)
        run.history["lai"].append(run.lai)
        run.append_biomass_and_interception(par=par)
        run.append_root_and_stage()
        run.append_layers(day_index=i)
        run.append_weather(rain=rain, rec=rec, tmean=tmean)
        run.append_n_total()
        run.append_microbes()
        run.append_enzyme_groups()

    return run.history, profile
