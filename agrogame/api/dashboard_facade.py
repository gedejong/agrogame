"""Public façade between ``agrogame.dashboard`` and the simulation engine.

The Streamlit dashboard used to import directly from
``agrogame.{soil,plant,weather,atmosphere,sim}.*`` — concrete cycles,
event types, profile dataclasses, and the orchestrator. That gripped the
engine's internal types and made every refactor risk dashboard breakage
(see #309 / ADR-011).

This module is the *only* surface the dashboard talks to. Everything
exported here is stable contract: rename a re-export and the dashboard
breaks loudly with an import error; rename something inside the engine
and the façade absorbs it.

Lives under ``agrogame.api`` because the dashboard is a second consumer
of the public engine surface — Godot consumes it over HTTP, the
dashboard consumes it in-process. The façade gives the in-process path
the same "stable contract" guarantee the HTTP layer already provides.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

# Re-exports — every type the dashboard names. Keep these public; rename
# downstream and update both this list and `__all__` together.
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

__all__ = [
    # Types the dashboard names directly.
    "SoilProfile",
    "DailyDrivers",
    "WeatherRecord",
    "PhenologyStage",
    "EtParams",
    "Evapotranspiration",
    "EnzymeGroupTotals",
    "NitrogenCycle",
    # Helpers.
    "load_soil_profile",
    "load_weather_records",
    "compute_vpd",
    # Run wrapper + history dict shape.
    "DailyAggregation",
    "DashboardSimulationRun",
    "new_history",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_soil_profile(
    name: str = "loam_temperate",
    presets_path: Path | None = None,
) -> SoilProfile:
    """Load a single named soil profile from the YAML preset library.

    Defaults to ``loam_temperate`` (the dashboard's default scenario).
    """
    path = presets_path or Path("data/soils/presets.yaml")
    return load_soil_presets(path).soils[name]


def load_weather_records(weather_file: Path) -> list[WeatherRecord]:
    """Load a weather file and return its records as a plain list."""
    return list(load_weather(weather_file).records)


def compute_vpd(temp_c: float, relative_humidity_pct: float) -> float:
    """Saturation-deficit VPD (kPa) from temperature and RH."""
    return vpd_kpa(temp_c, relative_humidity_pct)


# ---------------------------------------------------------------------------
# DailyAggregation + run wrapper
# ---------------------------------------------------------------------------


@dataclass
class DailyAggregation:
    """Per-day accumulator filled by event subscribers in ``DashboardSimulationRun``."""

    evap_mm: float = 0.0
    transp_mm: float = 0.0
    enzyme_totals: dict[str, float] = field(default_factory=dict)
    # Stress signals captured from events (optional; fall back to derived).
    water_stress: float | None = None
    n_stress: float | None = None
    p_stress: float | None = None


class DashboardSimulationRun:
    """In-process orchestrator + event subscribers + history-dict builder.

    Wraps ``FullSimulationOrchestrator`` and the six event subscribers
    the dashboard relies on (water/N stress, enzyme totals, evaporation,
    transpiration, microbial activity). Responsible for:

    - constructing the orchestrator and ET helper for a profile,
    - subscribing to engine events to fill a ``DailyAggregation``,
    - keeping a per-layer microbial-activity buffer,
    - allocating + appending to the time-series ``history`` dict.

    The dashboard never sees engine event types directly — it only hands
    in inputs (weather, schedules) and reads the resulting ``history``.
    """

    def __init__(self, profile: SoilProfile) -> None:
        """Construct the orchestrator and subscribe to all dashboard events."""
        self.profile = profile
        self.orch = FullSimulationOrchestrator(profile)
        self.et_mod = Evapotranspiration(EtParams())
        self.agg = self._subscribe_daily_aggregators()
        self.activity_layers: list[float] = self._subscribe_activity_capture(
            n_layers=len(profile.layers)
        )
        self.history: dict[str, Any] = new_history(profile)
        # Capture phenology thresholds once (used by progress bars).
        thr = getattr(getattr(self.orch, "phenology", None), "params", None)
        thresholds = getattr(thr, "thresholds", None)
        if thresholds is not None:
            self.history["thr_emergence"] = thresholds.emergence_gdd
            self.history["thr_flowering"] = thresholds.flowering_gdd
            self.history["thr_maturity"] = thresholds.maturity_gdd

    # ----- subscriber wiring -----

    def _subscribe_daily_aggregators(self) -> DailyAggregation:
        agg = DailyAggregation()

        def _on_evap(ev: EvaporationTaken) -> None:
            agg.evap_mm += float(ev.amount_mm)

        def _on_transp(ev: TranspirationByLayer) -> None:
            total = float(getattr(ev, "total_mm", sum(ev.amounts_mm)))
            agg.transp_mm += total

        bus = self.orch.event_bus
        bus.subscribe(EvaporationTaken, _on_evap)
        bus.subscribe(TranspirationByLayer, _on_transp)
        bus.subscribe(
            EnzymeGroupTotals,
            lambda ev: agg.enzyme_totals.update(ev.totals_c_kg_ha_by_group),
        )
        bus.subscribe(
            WaterStressComputed,
            lambda ev: setattr(agg, "water_stress", float(ev.stress)),
        )

        def _on_nutrient(ev: NutrientStressComputed) -> None:
            s = float(ev.stress)
            if str(ev.nutrient).upper() == "N":
                agg.n_stress = s
            elif str(ev.nutrient).upper() == "P":
                agg.p_stress = s

        bus.subscribe(NutrientStressComputed, _on_nutrient)
        return agg

    def _subscribe_activity_capture(self, n_layers: int) -> list[float]:
        """Subscribe to ``MicrobialActivityComputed`` and keep a per-layer buffer."""
        activity_layers: list[float] = [0.0] * n_layers

        def _on_activity(ev: MicrobialActivityComputed) -> None:
            if 0 <= ev.layer < n_layers:
                activity_layers[ev.layer] = float(ev.activity_index)

        self.orch.event_bus.subscribe(MicrobialActivityComputed, _on_activity)
        return activity_layers

    # ----- per-day driving -----

    def reset_daily_counters(self) -> None:
        """Clear per-day ET counters before stepping the orchestrator one day."""
        self.agg.evap_mm = 0.0
        self.agg.transp_mm = 0.0

    def step_day(
        self, drivers: DailyDrivers, *, tmin_c: float, tmax_c: float, par_mj_m2: float
    ) -> None:
        """Advance the orchestrator one day with the supplied drivers + climate."""
        self.orch.step_day(
            drivers=drivers, tmin_c=tmin_c, tmax_c=tmax_c, par_mj_m2=par_mj_m2
        )

    # ----- diagnostics -----

    def compute_reference_et(
        self, rec: WeatherRecord
    ) -> tuple[float, float | None, float, float, float, float]:
        """Compute ET₀ (PM, PT), VPD, and thermal/energy inputs for one day.

        Returns ``(et0_pm, et0_pt, par, rn, tmean, vpd)``.
        """
        par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        et0_pm = self.et_mod.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        try:
            et0_pt = self.et_mod.priestley_taylor(
                temp_mean_c=tmean, net_radiation_mj_m2=rn
            )
        except (ValueError, TypeError) as e:
            raise RuntimeError(
                f"Priestley-Taylor ET failed for tmean={tmean}, rn={rn}"
            ) from e
        vpd = vpd_kpa(tmean, rec.relative_humidity_pct or 60.0)
        return et0_pm, et0_pt, par, rn, tmean, vpd

    def calc_stress(
        self, *, vpd: float, lai: float, transp_mm: float, et0_mm: float
    ) -> tuple[float, float]:
        """Derive water-stress and stomatal proxies from ET and canopy state."""
        comps = self.et_mod.potential_components_with_vpd(
            et0_mm=et0_mm, lai=lai, vpd_kpa=vpd
        )
        demand = max(1e-6, comps.potential_transp_mm)
        water_stress = max(0.05, min(1.0, transp_mm / demand))
        vpd_excess = max(0.0, vpd - self.et_mod.params.vpd_ref_kpa)
        stomatal = max(0.2, 1.0 - self.et_mod.params.vpd_sensitivity * vpd_excess)
        return water_stress, stomatal

    # ----- engine state accessors (so dashboard never names *_state directly) -----

    @property
    def lai(self) -> float:
        """Current leaf area index from the canopy state."""
        return float(self.orch.canopy.state.lai or 0.0)

    @property
    def biomass_g_m2(self) -> float:
        """Current canopy biomass (g/m²)."""
        return float(self.orch.canopy.state.biomass_g_m2)

    @property
    def n_cycle(self) -> NitrogenCycle:
        """Direct handle to the nitrogen cycle for fertilizer application."""
        return self.orch.n_cycle

    # ----- history-dict appenders -----

    def append_day_summary(
        self, *, et0: float, water_stress: float, vpd: float, stomatal: float
    ) -> None:
        """Append the per-day ET / stress / vpd / stomatal block to history."""
        h = self.history
        agg = self.agg
        h["et0_mm"].append(et0)
        h["evap_mm"].append(float(agg.evap_mm))
        h["transp_mm"].append(float(agg.transp_mm))
        ws_any = getattr(agg, "water_stress", None)
        ws_val = float(water_stress) if ws_any is None else float(ws_any)
        h["water_stress"].append(ws_val)
        ns = getattr(agg, "n_stress", None)
        ps = getattr(agg, "p_stress", None)
        h["n_stress"].append(None if ns is None else float(ns))
        h["p_stress"].append(None if ps is None else float(ps))
        h["vpd_kpa"].append(vpd)
        h["stomatal"].append(stomatal)

    def append_biomass_and_interception(self, *, par: float) -> None:
        """Append today's biomass increment + canopy light interception."""
        h = self.history
        current_biomass = self.biomass_g_m2
        prev_biomass = h["biomass_g_m2"][-1] if h["biomass_g_m2"] else 0.0
        h["biomass_g_m2"].append(current_biomass)
        h["biomass_inc_g_m2"].append(max(0.0, current_biomass - prev_biomass))
        k_raw = getattr(self.orch.canopy.params, "extinction_coefficient_k", 0.6)
        if not isinstance(k_raw, int | float):
            raise TypeError("Canopy extinction coefficient must be numeric")
        k_ext = float(k_raw)
        lai_now = self.lai
        frac_int = (
            0.0 if lai_now <= 0.0 or par <= 0.0 else (1.0 - math.exp(-k_ext * lai_now))
        )
        h["par_mj_m2"].append(par)
        h["fraction_intercepted"].append(frac_int)
        h["par_intercepted_mj_m2"].append(par * frac_int)

    def append_root_and_stage(self) -> None:
        """Append today's root-depth + phenology-stage row."""
        h = self.history
        rd = getattr(getattr(self.orch, "root_state", None), "current_depth_cm", None)
        h["root_depth_cm"].append(float(rd) if isinstance(rd, int | float) else 0.0)
        stage = getattr(getattr(self.orch.phenology, "state", None), "stage", None)
        h["stage"].append(
            stage.value if isinstance(stage, PhenologyStage) else str(stage)
        )
        gdd = getattr(
            getattr(self.orch.phenology, "state", None), "accumulated_gdd", None
        )
        h["gdd_accum"].append(gdd if isinstance(gdd, int | float) else None)

    def append_layers(self, *, day_index: int) -> None:
        """Append today's per-layer θ / NO₃ / NH₄ snapshots."""
        h = self.history
        for li, _layer in enumerate(self.profile.layers):
            if len(h["theta_layers"][li]) == day_index:
                h["theta_layers"][li].append(self.orch.water_state.theta[li])
            else:
                h["theta_layers"][li][day_index] = self.orch.water_state.theta[li]
            if len(h["no3_layers"][li]) == day_index:
                h["no3_layers"][li].append(self.orch.n_state.no3[li])
                h["nh4_layers"][li].append(self.orch.n_state.nh4[li])
            else:
                h["no3_layers"][li][day_index] = self.orch.n_state.no3[li]
                h["nh4_layers"][li][day_index] = self.orch.n_state.nh4[li]

    def append_weather(self, *, rain: float, rec: WeatherRecord, tmean: float) -> None:
        """Append today's rainfall + temperature row."""
        h = self.history
        h["rain_mm"].append(rain)
        h["tmin_c"].append(rec.tmin_c)
        h["tmax_c"].append(rec.tmax_c)
        h["tmean_c"].append(tmean)

    def append_microbes(self) -> None:
        """Append today's profile-wide microbial C/N totals + fungal:bacterial avg."""
        h = self.history
        try:
            micro_c = sum(lc.c_kg_ha for lc in self.orch.microbes.state.layers)
            micro_n = sum(lc.n_kg_ha for lc in self.orch.microbes.state.layers)
            fb_avg = sum(
                lc.fungal_fraction for lc in self.orch.microbes.state.layers
            ) / max(1, len(self.orch.microbes.state.layers))
        except Exception:
            micro_c, micro_n, fb_avg = 0.0, 0.0, 0.4
        h["micro_c_total"].append(micro_c)
        h["micro_n_total"].append(micro_n)
        h["micro_fb_avg"].append(fb_avg)

    def append_enzyme_groups(self) -> None:
        """Append today's per-group enzyme C cost; reset the buffer for tomorrow."""
        h = self.history
        snapshot = dict(self.agg.enzyme_totals)
        h["enzyme_cellulase_c"].append(float(snapshot.get("cellulase", 0.0)))
        h["enzyme_protease_c"].append(float(snapshot.get("protease", 0.0)))
        h["enzyme_phosphatase_c"].append(float(snapshot.get("phosphatase", 0.0)))
        h["enzyme_urease_c"].append(float(snapshot.get("urease", 0.0)))
        self.agg.enzyme_totals = {}

    def append_micro_activity(self, *, day_index: int) -> None:
        """Append today's average + per-layer microbial activity."""
        h = self.history
        if not self.activity_layers:
            return
        h["micro_activity_avg"].append(
            sum(self.activity_layers) / max(1, len(self.activity_layers))
        )
        for li, val in enumerate(self.activity_layers):
            if len(h["micro_activity_layers"][li]) == day_index:
                h["micro_activity_layers"][li].append(val)
            else:
                h["micro_activity_layers"][li][day_index] = val

    def append_n_total(self) -> None:
        """Append the profile-wide mineral N total (NO₃ + NH₄, kg/ha)."""
        self.history["n_total_kgha"].append(
            sum(self.orch.n_state.no3) + sum(self.orch.n_state.nh4)
        )


# ---------------------------------------------------------------------------
# Top-level helpers used by dashboard.simulation
# ---------------------------------------------------------------------------


def new_history(profile: SoilProfile) -> dict[str, Any]:
    """Allocate the full history dict structure for a soil profile."""
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
        "micro_c_total": [],
        "micro_n_total": [],
        "micro_fb_avg": [],
        "enzyme_cellulase_c": [],
        "enzyme_protease_c": [],
        "enzyme_phosphatase_c": [],
        "enzyme_urease_c": [],
        "micro_activity_avg": [],
        "micro_activity_layers": [[] for _ in profile.layers],
        "thr_emergence": None,
        "thr_flowering": None,
        "thr_maturity": None,
    }


def extend_weather_records(
    records: list[WeatherRecord], days: int
) -> list[WeatherRecord]:
    """Cycle weather records to fill ``days`` entries (preserves ordering)."""
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


def apply_fertilizers(
    n_cycle: NitrogenCycle,
    day_index: int,
    fert_ops: list[tuple[int, float, str, int]] | None,
    fert_map: Mapping[int, float] | None,
) -> None:
    """Apply scheduled fertilizers for ``day_index`` (urea / AN, optional layer)."""
    if fert_ops:
        for d, amt, ftype, layer_idx in fert_ops:
            if d == day_index and amt > 0.0:
                if ftype == "urea":
                    n_cycle.apply_urea(layer=layer_idx, amount_kg_ha=amt)
                else:
                    n_cycle.apply_ammonium_nitrate(layer=layer_idx, amount_kg_ha=amt)
        return
    if fert_map:
        amt_simple = float(fert_map.get(day_index, 0.0))
        if amt_simple > 0.0:
            n_cycle.apply_ammonium_nitrate(layer=0, amount_kg_ha=amt_simple)


def make_drivers(total_rain_mm: float) -> DailyDrivers:
    """Build a ``DailyDrivers`` instance with rainfall only (irrigation+evap=0)."""
    return DailyDrivers(
        rainfall_mm=total_rain_mm, irrigation_mm=0.0, evaporation_mm=0.0
    )


__all__ = [
    *__all__,
    "extend_weather_records",
    "apply_fertilizers",
    "make_drivers",
]
