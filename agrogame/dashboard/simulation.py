from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from agrogame.atmosphere.et import EtParams, Evapotranspiration
from agrogame.plant.events import NutrientStressComputed, WaterStressComputed
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.microbes.events import EnzymeGroupTotals, MicrobialActivityComputed
from agrogame.soil.models import SoilProfile
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phenology.types import PhenologyStage
from agrogame.soil.water.events import EvaporationTaken, TranspirationByLayer
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather
from agrogame.weather.types import WeatherRecord
from agrogame.weather.utils import vpd_kpa


def _extend_weather_records(
    records: list[WeatherRecord], days: int
) -> list[WeatherRecord]:
    """Extend records by cycling existing days to reach requested length.

    This keeps the original ordering and increments the day field sequentially.
    """
    if days <= len(records) or not records:
        return records
    out = list(records)
    last_day = out[-1].day
    base = list(records)
    k = 0
    while len(out) < days:
        tmpl = base[k % len(base)]
        k += 1
        last_day = last_day + timedelta(days=1)
        out.append(
            WeatherRecord(
                day=last_day,
                tmin_c=tmpl.tmin_c,
                tmax_c=tmpl.tmax_c,
                relative_humidity_pct=tmpl.relative_humidity_pct,
                wind_m_s=tmpl.wind_m_s,
                shortwave_mj_m2=tmpl.shortwave_mj_m2,
                net_radiation_mj_m2=tmpl.net_radiation_mj_m2,
                albedo=tmpl.albedo,
                precip_mm=tmpl.precip_mm,
            )
        )
    return out


def _apply_fertilizers(
    ncycle: NitrogenCycle,
    i: int,
    fert_ops: list[tuple[int, float, str, int]] | None,
    fert_map: Mapping[int, float] | None,
) -> None:
    """Apply fertilizer operations for the current day index.

    Supports the detailed ops (type + layer) or a backward-compatible map.
    """
    if fert_ops:
        for d, amt, ftype, layer_idx in fert_ops:
            if d == i and amt > 0.0:
                if ftype == "urea":
                    ncycle.apply_urea(layer=layer_idx, amount_kg_ha=amt)
                else:
                    ncycle.apply_ammonium_nitrate(layer=layer_idx, amount_kg_ha=amt)
        return
    if fert_map:
        amt_simple = float(fert_map.get(i, 0.0))
        if amt_simple > 0.0:
            ncycle.apply_ammonium_nitrate(layer=0, amount_kg_ha=amt_simple)


def _compute_reference_et(
    et_mod: Evapotranspiration,
    rec: WeatherRecord,
) -> tuple[float, Optional[float], float, float, float, float]:
    """Compute ET0 (PM, PT), VPD and thermal/energy inputs used downstream.

    Returns (et0_pm, et0_pt, par, rn, tmean, vpd).
    """
    par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
    rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
    tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
    et0_pm = et_mod.et0(
        temp_mean_c=tmean,
        net_radiation_mj_m2=rn,
        method="penman-monteith",
        wind_m_s=rec.wind_m_s or 2.0,
        relative_humidity_pct=rec.relative_humidity_pct or 60.0,
    )
    # Fail-fast: PT should not raise under normal conditions; re-raise with context
    try:
        et0_pt = et_mod.priestley_taylor(temp_mean_c=tmean, net_radiation_mj_m2=rn)
    except (ValueError, TypeError) as e:
        raise RuntimeError(
            f"Priestley-Taylor ET failed for tmean={tmean}, rn={rn}"
        ) from e
    vpd = vpd_kpa(tmean, rec.relative_humidity_pct or 60.0)
    return et0_pm, et0_pt, par, rn, tmean, vpd


@dataclass
class _DailyAggregation:
    evap_mm: float = 0.0
    transp_mm: float = 0.0
    enzyme_totals: Dict[str, float] = field(default_factory=dict)
    # Stress signals captured from events (optional; fall back to derived)
    water_stress: Optional[float] = None
    n_stress: Optional[float] = None
    p_stress: Optional[float] = None


def _subscribe_daily_aggregators(orch: FullSimulationOrchestrator) -> _DailyAggregation:
    agg = _DailyAggregation()

    def _on_evap(ev: EvaporationTaken) -> None:
        agg.evap_mm += float(ev.amount_mm)

    def _on_transp(ev: TranspirationByLayer) -> None:
        total = float(getattr(ev, "total_mm", sum(ev.amounts_mm)))
        agg.transp_mm += total

    orch.event_bus.subscribe(EvaporationTaken, _on_evap)
    orch.event_bus.subscribe(TranspirationByLayer, _on_transp)
    orch.event_bus.subscribe(
        EnzymeGroupTotals,
        lambda ev: agg.enzyme_totals.update(ev.totals_c_kg_ha_by_group),
    )
    # Stress subscribers
    orch.event_bus.subscribe(
        WaterStressComputed, lambda ev: setattr(agg, "water_stress", float(ev.stress))
    )

    def _on_nutrient(ev: NutrientStressComputed) -> None:
        s = float(ev.stress)
        if str(ev.nutrient).upper() == "N":
            agg.n_stress = s
        elif str(ev.nutrient).upper() == "P":
            agg.p_stress = s

    orch.event_bus.subscribe(NutrientStressComputed, _on_nutrient)
    return agg


def _subscribe_activity_capture(
    orch: FullSimulationOrchestrator, n_layers: int
) -> list[float]:
    """Subscribe to microbial activity and keep a per-layer buffer updated daily."""
    activity_layers: list[float] = [0.0] * n_layers

    def _on_activity(ev: MicrobialActivityComputed) -> None:
        if 0 <= ev.layer < n_layers:
            activity_layers[ev.layer] = float(ev.activity_index)

    orch.event_bus.subscribe(MicrobialActivityComputed, _on_activity)
    return activity_layers


def _calc_stress(
    et_mod: Evapotranspiration,
    *,
    vpd: float,
    lai: float,
    transp_mm: float,
    et0_mm: float,
) -> tuple[float, float]:
    comps = et_mod.potential_components_with_vpd(et0_mm=et0_mm, lai=lai, vpd_kpa=vpd)
    demand = max(1e-6, comps.potential_transp_mm)
    water_stress = max(0.05, min(1.0, transp_mm / demand))
    vpd_excess = max(0.0, vpd - et_mod.params.vpd_ref_kpa)
    stomatal = max(0.2, 1.0 - et_mod.params.vpd_sensitivity * vpd_excess)
    return water_stress, stomatal


def _make_drivers(total_rain_mm: float) -> DailyDrivers:
    return DailyDrivers(
        rainfall_mm=total_rain_mm, irrigation_mm=0.0, evaporation_mm=0.0
    )


def _append_day_summary(
    history: Dict[str, Any],
    *,
    et0: float,
    agg: _DailyAggregation,
    water_stress: float,
    vpd: float,
    stomatal: float,
) -> None:
    history["et0_mm"].append(et0)
    history["evap_mm"].append(float(agg.evap_mm))
    history["transp_mm"].append(float(agg.transp_mm))
    ws_any = getattr(agg, "water_stress", None)
    ws_val: float = float(water_stress)
    if ws_any is not None:
        ws_val = float(ws_any)
    history["water_stress"].append(ws_val)
    # Record nutrient stresses when available (None otherwise for alignment)
    ns = getattr(agg, "n_stress", None)
    ps = getattr(agg, "p_stress", None)
    history["n_stress"].append(None if ns is None else float(ns))
    history["p_stress"].append(None if ps is None else float(ps))
    history["vpd_kpa"].append(vpd)
    history["stomatal"].append(stomatal)


def _append_biomass_and_interception(
    history: Dict[str, Any], *, orch: FullSimulationOrchestrator, par: float
) -> None:
    current_biomass = orch.canopy.state.biomass_g_m2
    prev_biomass = history["biomass_g_m2"][-1] if history["biomass_g_m2"] else 0.0
    history["biomass_g_m2"].append(current_biomass)
    history["biomass_inc_g_m2"].append(max(0.0, current_biomass - prev_biomass))
    k_raw = getattr(orch.canopy.params, "extinction_coefficient_k", 0.6)
    if not isinstance(k_raw, (int, float)):
        raise TypeError("Canopy extinction coefficient must be numeric")
    k_ext = float(k_raw)
    lai_now = float(orch.canopy.state.lai or 0.0)
    frac_int = (
        0.0 if lai_now <= 0.0 or par <= 0.0 else (1.0 - math.exp(-k_ext * lai_now))
    )
    history["par_mj_m2"].append(par)
    history["fraction_intercepted"].append(frac_int)
    history["par_intercepted_mj_m2"].append(par * frac_int)


def _append_root_and_stage(
    history: Dict[str, Any], *, orch: FullSimulationOrchestrator
) -> None:
    rd = getattr(getattr(orch, "root_state", None), "current_depth_cm", None)
    history["root_depth_cm"].append(float(rd) if isinstance(rd, (int, float)) else 0.0)
    stage = getattr(getattr(orch.phenology, "state", None), "stage", None)
    history["stage"].append(
        stage.value if isinstance(stage, PhenologyStage) else str(stage)
    )
    gdd = getattr(getattr(orch.phenology, "state", None), "accumulated_gdd", None)
    history["gdd_accum"].append(gdd if isinstance(gdd, (int, float)) else None)


def _append_layers(
    history: Dict[str, Any],
    *,
    orch: FullSimulationOrchestrator,
    profile: SoilProfile,
    day_index: int,
) -> None:
    for li, _layer in enumerate(profile.layers):
        if len(history["theta_layers"][li]) == day_index:
            history["theta_layers"][li].append(orch.water_state.theta[li])
        else:
            history["theta_layers"][li][day_index] = orch.water_state.theta[li]
        if len(history["no3_layers"][li]) == day_index:
            history["no3_layers"][li].append(orch.n_state.no3[li])
            history["nh4_layers"][li].append(orch.n_state.nh4[li])
        else:
            history["no3_layers"][li][day_index] = orch.n_state.no3[li]
            history["nh4_layers"][li][day_index] = orch.n_state.nh4[li]


def _append_weather(
    history: Dict[str, Any], *, rain: float, rec: WeatherRecord, tmean: float
) -> None:
    history["rain_mm"].append(rain)
    history["tmin_c"].append(rec.tmin_c)
    history["tmax_c"].append(rec.tmax_c)
    history["tmean_c"].append(tmean)


def _append_microbes(
    history: Dict[str, Any], *, orch: FullSimulationOrchestrator
) -> None:
    try:
        micro_c = sum(lc.c_kg_ha for lc in orch.microbes.state.layers)
        micro_n = sum(lc.n_kg_ha for lc in orch.microbes.state.layers)
        fb_avg = sum(lc.fungal_fraction for lc in orch.microbes.state.layers) / max(
            1, len(orch.microbes.state.layers)
        )
    except Exception:
        micro_c, micro_n, fb_avg = 0.0, 0.0, 0.4
    history["micro_c_total"].append(micro_c)
    history["micro_n_total"].append(micro_n)
    history["micro_fb_avg"].append(fb_avg)


def _append_enzyme_groups(history: Dict[str, Any], *, agg: _DailyAggregation) -> None:
    snapshot = dict(agg.enzyme_totals)
    history["enzyme_cellulase_c"].append(float(snapshot.get("cellulase", 0.0)))
    history["enzyme_protease_c"].append(float(snapshot.get("protease", 0.0)))
    history["enzyme_phosphatase_c"].append(float(snapshot.get("phosphatase", 0.0)))
    history["enzyme_urease_c"].append(float(snapshot.get("urease", 0.0)))
    agg.enzyme_totals = {}


# Removed legacy ET partition helper; actual ET is captured via events


def _init_orchestrator(
    profile: SoilProfile,
) -> tuple[FullSimulationOrchestrator, Evapotranspiration]:
    """Build a full orchestrator and ET helper for diagnostics."""
    orch = FullSimulationOrchestrator(profile)
    et_mod = Evapotranspiration(EtParams())
    return orch, et_mod


def _new_history(profile: SoilProfile) -> Dict[str, Any]:
    """Allocate the history structure for time series outputs."""
    return {
        "day": [],
        "lai": [],
        "biomass_g_m2": [],
        "biomass_inc_g_m2": [],
        "theta_layers": [[] for _ in profile.layers],
        "no3_layers": [[] for _ in profile.layers],
        "nh4_layers": [[] for _ in profile.layers],
        "root_depth_cm": [],
        "stage": [],
        "gdd_accum": [],
        "rain_mm": [],
        "tmin_c": [],
        "tmax_c": [],
        "tmean_c": [],
        "par_mj_m2": [],
        "par_intercepted_mj_m2": [],
        "fraction_intercepted": [],
        "et0_mm": [],
        "et0_pt_mm": [],
        "evap_mm": [],
        "transp_mm": [],
        "vpd_kpa": [],
        "stomatal": [],
        "water_stress": [],
        "n_stress": [],
        "p_stress": [],
        "n_total_kgha": [],
        # Microbes totals and proxies
        "micro_c_total": [],
        "micro_n_total": [],
        "micro_fb_avg": [],
        # Enzyme group totals (C cost per day)
        "enzyme_cellulase_c": [],
        "enzyme_protease_c": [],
        "enzyme_phosphatase_c": [],
        "enzyme_urease_c": [],
        # Microbial activity (average and by layer)
        "micro_activity_avg": [],
        "micro_activity_layers": [[] for _ in profile.layers],
        # phenology thresholds (for progress bar)
        "thr_emergence": None,
        "thr_flowering": None,
        "thr_maturity": None,
    }


def _run_simulation(
    days: int,
    weather_file: Path,
    irrigation_schedule: list[tuple[int, float]] | None = None,
    fertilizer_schedule: list[tuple[int, float]] | None = None,
    *,
    fertilizer_ops: list[tuple[int, float, str, int]] | None = None,
) -> tuple[Dict[str, Any], SoilProfile]:
    soil_lib = load_soil_presets(Path("data/soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    orch, et_mod = _init_orchestrator(profile)
    agg = _subscribe_daily_aggregators(orch)
    activity_layers = _subscribe_activity_capture(orch, n_layers=len(profile.layers))

    weather = load_weather(weather_file)
    records: list[WeatherRecord] = _extend_weather_records(list(weather.records), days)

    history: Dict[str, Any] = _new_history(profile)

    irrig_map = dict(irrigation_schedule or [])
    fert_map = dict(fertilizer_schedule or [])
    fert_ops = list(fertilizer_ops or [])

    # Capture phenology thresholds once for progress computation
    thr = getattr(getattr(orch, "phenology", None), "params", None)
    thresholds = getattr(thr, "thresholds", None)
    if thresholds is not None:
        history["thr_emergence"] = thresholds.emergence_gdd
        history["thr_flowering"] = thresholds.flowering_gdd
        history["thr_maturity"] = thresholds.maturity_gdd

    # Aggregation now handled by helper; keep code flatter for complexity

    for i in range(min(days, len(records))):
        rec = records[i]
        rain = rec.precip_mm or 0.0
        irrigation = irrig_map.get(i, 0.0)

        _apply_fertilizers(orch.n_cycle, i, fert_ops, fert_map)

        et0, et0_pt, par, rn, tmean, vpd = _compute_reference_et(et_mod, rec)
        history["et0_mm"].append(et0)
        history["et0_pt_mm"].append(et0_pt)

        # Reset daily ET counters and advance one day via Calendar/DayTick
        agg.evap_mm = 0.0
        agg.transp_mm = 0.0
        drivers = _make_drivers(rain + irrigation)
        orch.step_day(
            drivers=drivers,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
        )

        # Derive water stress and stomatal proxy
        water_stress, stomatal = _calc_stress(
            et_mod,
            vpd=vpd,
            lai=orch.canopy.state.lai,
            transp_mm=agg.transp_mm,
            et0_mm=et0,
        )
        _append_day_summary(
            history,
            et0=et0,
            agg=agg,
            water_stress=water_stress,
            vpd=vpd,
            stomatal=stomatal,
        )
        # Microbial activity capture (average and by layer)
        if activity_layers:
            history["micro_activity_avg"].append(
                sum(activity_layers) / max(1, len(activity_layers))
            )
            for li, val in enumerate(activity_layers):
                if len(history["micro_activity_layers"][li]) == i:
                    history["micro_activity_layers"][li].append(val)
                else:
                    history["micro_activity_layers"][li][i] = val

        # Nitrogen status proxy now reflects orchestrator-run cycles

        history["day"].append(rec.day)
        history["lai"].append(orch.canopy.state.lai)
        _append_biomass_and_interception(history, orch=orch, par=par)
        _append_root_and_stage(history, orch=orch)
        _append_layers(history, orch=orch, profile=profile, day_index=i)
        _append_weather(history, rain=rain, rec=rec, tmean=tmean)
        # Aggregate N status proxy (total mineral N across layers)
        history["n_total_kgha"].append(sum(orch.n_state.no3) + sum(orch.n_state.nh4))
        _append_microbes(history, orch=orch)

        _append_enzyme_groups(history, agg=agg)

    return history, profile
