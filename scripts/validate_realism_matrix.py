#!/usr/bin/env python
"""Realism validation matrix for the simulation engine.

Runs full-season simulations outside the game for every crop preset on every
soil preset under every climate preset, plus drought, wet and hot weather
scenarios on a subset, and grades the season ledgers against expectation
bands drawn from the crop-modelling literature (DSSAT, APSIM and WOFOST
parameter ranges, FAO-56, Global Yield Gap Atlas) and against internal
consistency invariants (water and nitrogen mass balance, monotonic
trajectories, soil contrasts, stress directions, regression anchors).

The harness never changes the engine: everything it reports is a
measurement. Checks tagged as known limitations are reported apart from new
findings so that the two are never confused.

Outputs under ``out/validation/<tag>/`` (``out/validation/latest`` points at
the newest tag):

    runs.csv      one row per run, every season scalar
    findings.csv  one row per band violation
    report.md     graded summary
    daily/        per-run daily trajectories (failed runs; all with --daily)
    plots/        trajectories and ledgers (with --plots)

Examples::

    poetry run python scripts/validate_realism_matrix.py --list
    poetry run python scripts/validate_realism_matrix.py --plots
    poetry run python scripts/validate_realism_matrix.py --crops maize \\
        --soils loam_temperate --climates kenya_highlands \\
        --no-stress-matrix --daily
"""

from __future__ import annotations

import argparse
import copy
import csv
import math
import statistics
import subprocess
import sys
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from itertools import pairwise, product
from pathlib import Path
from typing import Any

from agrogame.atmosphere.et.events import EvapotranspirationComputed
from agrogame.events import EventBus
from agrogame.plant.events import NutrientStressComputed, PlantNUptakeComputed
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.canopy.events import (
    CanopyEvaporated,
    CanopyIntercepted,
    DroughtSenescenceApplied,
    FrostDamageApplied,
    HeatDamageApplied,
)
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.micronutrients.constants import (
    CRITICAL_FE_PPM,
    CRITICAL_ZN_PPM,
    TOXIC_FE_PPM,
)
from agrogame.soil.nitrogen.events import (
    DenitrificationOccurred,
    MassFlowNSupplyComputed,
    NitrificationOccurred,
    NutrientLeached,
    VolatilizationOccurred,
)
from agrogame.soil.phenology.events import StageChanged
from agrogame.soil.redox.events import N2OEmitted
from agrogame.soil.som.events import CO2Respired, SOMDecomposed
from agrogame.soil.water.constants import TEXTURE_TO_CN
from agrogame.soil.water.events import (
    EvaporationTaken,
    RunoffGenerated,
    TranspirationByLayer,
    WaterDrained,
)
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
CROP_PRESETS = DATA_DIR / "crops" / "presets.yaml"
CLIMATE_PRESETS = DATA_DIR / "climate" / "presets.yaml"
SOIL_PRESETS = DATA_DIR / "soils" / "presets.yaml"
DEFAULT_OUT = REPO_ROOT / "out" / "validation"

# ---------------------------------------------------------------------------
# Matrix definition
# ---------------------------------------------------------------------------

NL = "netherlands_temperate"
KENYA = "kenya_highlands"
SAHEL = "sahel_arid"
ALL_CLIMATES: tuple[str, ...] = (NL, KENYA, SAHEL)
ALL_CROPS: tuple[str, ...] = (
    "maize",
    "winter_wheat",
    "spring_wheat",
    "rice",
    "sorghum",
    "soybean",
    "grape",
)
ALL_SOILS: tuple[str, ...] = (
    "sandy_arid",
    "sandy_temperate",
    "loam_temperate",
    "clay_temperate",
    "clay_netherlands",
    "sandy_loam_temperate",
    "clay_loam_temperate",
    "peat_cool_wet",
    "sandy_subsaharan",
)
STRESS_SCENARIOS: tuple[str, ...] = ("drought", "wet", "hot")
ALL_SCENARIOS: tuple[str, ...] = ("normal", *STRESS_SCENARIOS)
STRESS_CROPS: tuple[str, ...] = ("maize", "spring_wheat", "sorghum")
STRESS_SOILS: tuple[str, ...] = ("sandy_temperate", "loam_temperate", "clay_temperate")
TEMPERATE_TRIO: tuple[str, ...] = STRESS_SOILS
CEREALS: tuple[str, ...] = ("maize", "winter_wheat", "spring_wheat", "rice", "sorghum")
WHEATS: tuple[str, ...] = ("winter_wheat", "spring_wheat")
DEFAULT_SEED = 42
NOT_REACHED = -1
# Soils holding less initial SOM-C than this are treated as SOM-poor: their
# nitrogen supply is expected to limit the crop rather than feed it.
LOW_SOM_C_KG_HA = 40_000.0
# Canopy is counted as present (for stress-day statistics) above this LAI.
ACTIVE_LAI = 0.1
# Nutrients whose stresses the canopy combines as a Liebig minimum, in report
# order; water multiplies that minimum and is tracked as its own factor.
NUTRIENTS: tuple[str, ...] = ("N", "P", "S", "FE", "ZN", "MN")
LIMITING_FACTORS: tuple[str, ...] = (*NUTRIENTS, "WATER")
# A stress factor this close to 1 is treated as non-limiting.
STRESS_ACTIVE = 0.999
# Oxygen fraction below which the gas module flags a layer anaerobic.
ANOXIC_O2_FRAC = 0.02

# How well each crop fits each climate. "not_grown" combinations still run
# (they exercise vernalisation and heat limits) but only invariants and
# must-not-thrive checks are applied to them.
CROP_CLIMATE_FIT: dict[tuple[str, str], str] = {
    ("maize", NL): "typical",
    ("maize", KENYA): "typical",
    ("maize", SAHEL): "typical",
    ("sorghum", SAHEL): "typical",
    ("sorghum", NL): "marginal",
    ("sorghum", KENYA): "marginal",
    ("spring_wheat", NL): "typical",
    ("spring_wheat", KENYA): "typical",
    ("spring_wheat", SAHEL): "not_grown",
    ("winter_wheat", NL): "typical",
    ("winter_wheat", KENYA): "not_grown",
    ("winter_wheat", SAHEL): "not_grown",
    ("rice", KENYA): "typical",
    ("rice", SAHEL): "marginal",
    ("rice", NL): "not_grown",
    ("soybean", KENYA): "typical",
    ("soybean", NL): "marginal",
    ("soybean", SAHEL): "marginal",
    ("grape", NL): "typical",
    ("grape", KENYA): "typical",
    ("grape", SAHEL): "not_grown",
}

TEXTURE_CLASS: dict[str, str] = {
    "sand": "SAND",
    "sandy_loam": "SANDY_LOAM",
    "loam": "LOAM",
    "clay_loam": "CLAY_LOAM",
    "clay": "CLAY",
    "peat": "PEAT",
}
DRAINAGE_CLASS: dict[str, str] = {
    "SAND": "LIGHT",
    "SANDY_LOAM": "LIGHT",
    "LOAM": "MEDIUM",
    "CLAY_LOAM": "MEDIUM",
    "PEAT": "MEDIUM",
    "CLAY": "HEAVY",
}
# The climate each soil preset was described for. Nitrogen-supply and SOM
# bands are relaxed to WARN when a soil runs under another climate.
SOIL_HOME_CLIMATE: dict[str, str] = {
    "sandy_arid": SAHEL,
    "sandy_subsaharan": KENYA,
}


def season_for(crop: str, climate: str) -> tuple[date, int]:
    """Sowing date and season length (days) matching the realism test suite.

    Kenya uses 180 days for every crop: net growth stops at physiological
    maturity, so a crop that matures earlier is unaffected by the longer
    window.
    """
    if climate == NL:
        if crop == "winter_wheat":
            return date(2023, 10, 15), 280
        return date(2024, 4, 1), 150
    if climate == KENYA:
        return date(2024, 3, 1), 180
    if climate == SAHEL:
        return date(2024, 6, 1), 150
    raise ValueError(f"no sowing calendar for climate {climate!r}")


@dataclass(frozen=True)
class Management:
    """Season management. The matrix runs unfertilised and rain-fed."""

    fertilizer_kg: float = (
        0.0  # urea applied at sowing, kg/ha as accepted by the engine
    )
    daily_irrigation_mm: float = 0.0


@dataclass(frozen=True)
class RunSpec:
    crop: str
    soil: str
    climate: str
    sowing_date: date
    days: int
    scenario: str = "normal"
    seed: int = DEFAULT_SEED
    fit: str = "typical"
    management: Management = field(default_factory=Management)

    @property
    def run_id(self) -> str:
        return (
            f"{self.crop}__{self.soil}__{self.climate}__{self.scenario}__s{self.seed}"
        )

    @property
    def viable(self) -> bool:
        return self.fit != "not_grown"


def make_spec(
    crop: str,
    soil: str,
    climate: str,
    scenario: str,
    seed: int,
    sowing: date | None = None,
    days: int | None = None,
) -> RunSpec:
    default_sowing, default_days = season_for(crop, climate)
    return RunSpec(
        crop=crop,
        soil=soil,
        climate=climate,
        sowing_date=sowing or default_sowing,
        days=days or default_days,
        scenario=scenario,
        seed=seed,
        fit=CROP_CLIMATE_FIT.get((crop, climate), "marginal"),
    )


def build_matrix(
    crops: Sequence[str],
    soils: Sequence[str],
    climates: Sequence[str],
    scenarios: Sequence[str],
    seeds: Sequence[int],
    stress_matrix: bool,
    sowing: date | None = None,
    days: int | None = None,
) -> list[RunSpec]:
    """Normal runs for the full crop x soil x climate product, then the stress
    scenarios on the stress subset. Normal runs are always included because
    the stress checks are relative to them."""
    specs: list[RunSpec] = []
    for seed in seeds:
        for crop, soil, climate in product(crops, soils, climates):
            specs.append(make_spec(crop, soil, climate, "normal", seed, sowing, days))
        if not stress_matrix:
            continue
        for scenario in scenarios:
            if scenario == "normal":
                continue
            for crop, soil, climate in product(crops, soils, climates):
                if crop not in STRESS_CROPS or soil not in STRESS_SOILS:
                    continue
                specs.append(
                    make_spec(crop, soil, climate, scenario, seed, sowing, days)
                )
    return specs


# ---------------------------------------------------------------------------
# Soil description
# ---------------------------------------------------------------------------


def _texture_name(texture: Any) -> str:
    return str(getattr(texture, "value", texture)).lower()


@dataclass(frozen=True)
class SoilInfo:
    key: str
    texture: str
    soil_class: str
    drainage: str
    home_climate: str
    depths_cm: tuple[float, ...]
    field_capacity: tuple[float, ...]
    wilting_point: tuple[float, ...]
    saturation: tuple[float, ...]

    @property
    def profile_depth_cm(self) -> float:
        return sum(self.depths_cm)

    @property
    def pawc_mm(self) -> float:
        return sum(
            (fc - wp) * d * 10.0
            for fc, wp, d in zip(
                self.field_capacity, self.wilting_point, self.depths_cm, strict=True
            )
        )

    @property
    def wp_storage_mm(self) -> float:
        return sum(
            wp * d * 10.0
            for wp, d in zip(self.wilting_point, self.depths_cm, strict=True)
        )

    @property
    def curve_number_default(self) -> float:
        return float(TEXTURE_TO_CN.get(self.texture, math.nan))

    def storage_mm(self, theta: Sequence[float]) -> float:
        return sum(t * d * 10.0 for t, d in zip(theta, self.depths_cm, strict=True))


def describe_soil(key: str, profile: Any) -> SoilInfo:
    layers = list(profile.layers)
    texture = _texture_name(layers[0].texture)
    soil_class = TEXTURE_CLASS.get(texture, "OTHER")
    return SoilInfo(
        key=key,
        texture=texture,
        soil_class=soil_class,
        drainage=DRAINAGE_CLASS.get(soil_class, "MEDIUM"),
        home_climate=SOIL_HOME_CLIMATE.get(key, NL),
        depths_cm=tuple(float(layer.depth_cm) for layer in layers),
        field_capacity=tuple(float(layer.field_capacity) for layer in layers),
        wilting_point=tuple(float(layer.wilting_point) for layer in layers),
        saturation=tuple(float(layer.saturation) for layer in layers),
    )


@dataclass
class Libraries:
    crops: Any
    climates: Any
    soils: Any


def load_libraries() -> Libraries:
    libs = Libraries(
        crops=load_crop_presets(CROP_PRESETS),
        climates=load_climate_presets(CLIMATE_PRESETS),
        soils=load_soil_presets(SOIL_PRESETS),
    )
    missing = [s for s in ALL_SOILS if s not in libs.soils.soils]
    if missing:
        raise ValueError(f"soil presets missing from {SOIL_PRESETS}: {missing}")
    return libs


# ---------------------------------------------------------------------------
# Event collection
# ---------------------------------------------------------------------------

DAILY_FLUX_KEYS: tuple[str, ...] = (
    "et0_mm",
    "evap_mm",
    "transp_mm",
    "evap_taken_mm",
    "transp_taken_mm",
    "intercept_mm",
    "canopy_evap_mm",
    "runoff_mm",
    "deep_perc_mm",
    "no3_leached_kg_ha",
    "nh4_leached_kg_ha",
    "so4_leached_kg_ha",
    "nitrification_kg_ha",
    "denitrification_kg_ha",
    "volatilization_kg_ha",
    "n2o_kg_n_ha",
    "som_min_n_kg_ha",
    "som_dec_c_kg_ha",
    "co2_c_kg_ha",
    "n_uptake_kg_ha",
    "n_massflow_supply_kg_ha",
    "frost_events",
    "heat_events",
    "drought_senescence_events",
    "frost_biomass_loss_g_m2",
)


def _is_deep_percolation(event: Any) -> bool:
    return int(event.to_layer) == -1


def _nutrient_filter(name: str) -> Callable[[Any], bool]:
    def matches(event: Any) -> bool:
        nutrient = str(getattr(event.nutrient, "value", event.nutrient)).upper()
        return nutrient == name

    return matches


class FluxCollector:
    """Accumulates engine events into per-day flux totals.

    Every flux is booked from the event the engine emits for it; the
    potential nitrate supply by transpiration mass flow arrives as the
    nitrogen module's ``MassFlowNSupplyComputed`` diagnostic, which debits
    nothing (plant uptake is demand-driven and availability-capped).
    """

    def __init__(self) -> None:
        self.today: dict[str, float] = dict.fromkeys(DAILY_FLUX_KEYS, 0.0)
        self.stage_days: dict[str, int] = {}
        self.curve_number = math.nan
        self._orch: FullSimulationOrchestrator | None = None
        self._day = 0
        self.nutrient_stress: dict[str, float] = dict.fromkeys(NUTRIENTS, 1.0)

    def start_day(self, day_index: int) -> None:
        self._day = day_index
        self.today = dict.fromkeys(DAILY_FLUX_KEYS, 0.0)
        self.nutrient_stress = dict.fromkeys(NUTRIENTS, 1.0)

    def subscribe_post(self, bus: EventBus, orch: FullSimulationOrchestrator) -> None:
        self._orch = orch
        bus.subscribe(RunoffGenerated, self._on_runoff)
        bus.subscribe(StageChanged, self._on_stage)
        bus.subscribe(NutrientStressComputed, self._on_nutrient_stress)
        add = self._add
        add(bus, EvapotranspirationComputed, "et0_mm", "et0_mm")
        add(bus, EvapotranspirationComputed, "evap_mm", "evaporation_mm")
        add(bus, EvapotranspirationComputed, "transp_mm", "transpiration_mm")
        add(bus, EvaporationTaken, "evap_taken_mm", "amount_mm")
        add(bus, TranspirationByLayer, "transp_taken_mm", "total_mm")
        add(bus, MassFlowNSupplyComputed, "n_massflow_supply_kg_ha", "total_kg_ha")
        add(bus, CanopyIntercepted, "intercept_mm", "amount_mm")
        add(bus, CanopyEvaporated, "canopy_evap_mm", "amount_mm")
        add(bus, RunoffGenerated, "runoff_mm", "amount_mm")
        add(
            bus,
            WaterDrained,
            "deep_perc_mm",
            "amount_mm",
            predicate=_is_deep_percolation,
        )
        add(
            bus,
            NutrientLeached,
            "no3_leached_kg_ha",
            "amount_kg_ha",
            predicate=_nutrient_filter("NO3"),
        )
        add(
            bus,
            NutrientLeached,
            "nh4_leached_kg_ha",
            "amount_kg_ha",
            predicate=_nutrient_filter("NH4"),
        )
        add(
            bus,
            NutrientLeached,
            "so4_leached_kg_ha",
            "amount_kg_ha",
            predicate=_nutrient_filter("SO4"),
        )
        add(bus, NitrificationOccurred, "nitrification_kg_ha", "amount_kg_ha")
        add(bus, DenitrificationOccurred, "denitrification_kg_ha", "amount_kg_ha")
        add(bus, VolatilizationOccurred, "volatilization_kg_ha", "amount_kg_ha")
        add(bus, N2OEmitted, "n2o_kg_n_ha", "amount_kg_n_ha")
        add(bus, SOMDecomposed, "som_min_n_kg_ha", "mineralized_n_kg_ha")
        add(bus, SOMDecomposed, "som_dec_c_kg_ha", "decomposed_c_kg_ha")
        add(bus, CO2Respired, "co2_c_kg_ha", "co2_c_kg_ha")
        add(bus, PlantNUptakeComputed, "n_uptake_kg_ha", "uptake_kg_ha")
        add(bus, FrostDamageApplied, "frost_events")
        add(bus, FrostDamageApplied, "frost_biomass_loss_g_m2", "biomass_loss_g_m2")
        add(bus, HeatDamageApplied, "heat_events")
        add(bus, DroughtSenescenceApplied, "drought_senescence_events")

    def _add(
        self,
        bus: EventBus,
        event_type: type,
        key: str,
        attr: str | None = None,
        *,
        predicate: Callable[[Any], bool] | None = None,
    ) -> None:
        def handler(event: Any) -> None:
            if predicate is not None and not predicate(event):
                return
            self.today[key] += 1.0 if attr is None else float(getattr(event, attr))

        bus.subscribe(event_type, handler)

    def _on_nutrient_stress(self, event: Any) -> None:
        name = str(getattr(event.nutrient, "value", event.nutrient)).upper()
        if name in self.nutrient_stress:
            self.nutrient_stress[name] = min(
                self.nutrient_stress[name], float(event.stress)
            )

    def _on_runoff(self, event: Any) -> None:
        self.curve_number = float(event.curve_number)

    def _on_stage(self, event: Any) -> None:
        name = str(getattr(event.to_stage, "name", event.to_stage))
        self.stage_days.setdefault(name, self._day)


# ---------------------------------------------------------------------------
# Running one season
# ---------------------------------------------------------------------------


def read_state(orch: FullSimulationOrchestrator, soil: SoilInfo) -> dict[str, Any]:
    canopy = orch.canopy.state
    phen = orch.phenology.state
    roots = orch.root_state
    plant_n = orch.plant_n_state
    theta = [float(t) for t in orch.water_state.theta]
    som_layers = orch.som.state.layers
    row: dict[str, Any] = {
        "lai": float(canopy.lai),
        "agb_g_m2": float(canopy.biomass_g_m2),
        "grain_g_m2": float(canopy.grain_biomass_g_m2),
        "stem_g_m2": float(canopy.stem_biomass_g_m2),
        "water_stress": float(canopy.last_water_stress),
        "root_depth_cm": float(roots.current_depth_cm),
        "root_biomass_g_m2": float(roots.biomass_g_m2),
        "stage": str(phen.stage.name),
        "gdd": float(phen.accumulated_gdd),
        "vernalization_units": float(getattr(phen, "vernalization_units", 0.0)),
        "nni": float(plant_n.nni),
        "n_stress": float(plant_n.stress),
        "plant_n_kg_ha": float(plant_n.n_stock_kg_ha),
        "plant_n_pct": float(plant_n.actual_n_pct),
        "storage_mm": soil.storage_mm(theta),
        "no3_kg_ha": float(sum(orch.n_state.no3)),
        "nh4_kg_ha": float(sum(orch.n_state.nh4)),
        "som_c_kg_ha": float(sum(layer.total_c for layer in som_layers)),
        "som_n_kg_ha": float(sum(layer.total_n for layer in som_layers)),
        "microbial_c_kg_ha": float(
            sum(layer.c_kg_ha for layer in orch.microbes.state.layers)
        ),
        "ph_0": float(orch.chem_state.ph[0]),
        "eh_0_mv": float(orch.redox_state.eh_mv[0]),
        "o2_0_frac": float(orch.gas_state.o2_frac[0]),
        "co2_0_frac": float(orch.gas_state.co2_frac[0]),
        "anaerobic_layers": int(sum(bool(a) for a in orch.gas_state.anaerobic)),
        "fe_avail_0_ppm": float(orch.micro_state.fe_available[0]),
        "zn_avail_0_ppm": float(orch.micro_state.zn_available[0]),
        "s_avail_kg_ha": float(sum(orch.s_state.available_s)),
    }
    for j, value in enumerate(theta):
        row[f"theta_{j}"] = value
    return row


def _limitation_row(
    nutrient_stress: dict[str, float], water_stress: float
) -> dict[str, Any]:
    """Growth-limitation columns for one day.

    The canopy scales its potential growth by the Liebig minimum of the
    nutrient stresses times the water stress; the binding factor is the one
    that sets that product, or ``none`` when nothing limits.
    """
    factors = {**nutrient_stress, "WATER": float(water_stress)}
    binding = min(factors, key=factors.__getitem__)
    row: dict[str, Any] = {f"stress_{k.lower()}": v for k, v in factors.items()}
    row["growth_factor"] = min(nutrient_stress.values()) * float(water_stress)
    row["binding_factor"] = (
        binding.lower() if factors[binding] < STRESS_ACTIVE else "none"
    )
    return row


@dataclass
class RunResult:
    spec: RunSpec
    soil: SoilInfo
    status: str
    error: str
    traceback_tail: str
    runtime_s: float
    scalars: dict[str, Any]
    daily: list[dict[str, Any]]
    findings: list[Finding] = field(default_factory=list)
    grade: str = ""


def run_one(spec: RunSpec, libs: Libraries, *, debug_bus: bool = True) -> RunResult:
    t0 = time.perf_counter()
    crop = libs.crops.get_preset(spec.crop, spec.climate)
    climate = libs.climates.climates[spec.climate]
    profile = copy.deepcopy(libs.soils.soils[spec.soil])
    soil = describe_soil(spec.soil, profile)
    series = SyntheticWeatherGenerator(climate, seed=spec.seed).generate(
        spec.days, spec.sowing_date, scenario=spec.scenario
    )
    bus = EventBus(debug_mode=debug_bus)
    collector = FluxCollector()
    orch = FullSimulationOrchestrator(
        profile, event_bus=bus, crop=crop, latitude_deg=climate.latitude_deg
    )
    collector.subscribe_post(bus, orch)

    daily: list[dict[str, Any]] = []
    start: dict[str, Any] = {}
    status, error, tb_tail = "ok", "", ""
    day_index = NOT_REACHED
    try:
        start = read_state(orch, soil)
        for day_index, rec in enumerate(series.records):
            collector.start_day(day_index)
            if day_index == 0 and spec.management.fertilizer_kg > 0:
                orch.apply_fertilizer("urea", spec.management.fertilizer_kg)
            rain = float(rec.precip_mm or 0.0)
            irrigation = spec.management.daily_irrigation_mm
            shortwave = float(rec.shortwave_mj_m2 or 12.0)
            orch.step_day(
                drivers=DailyDrivers(rainfall_mm=rain, irrigation_mm=irrigation),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=shortwave,
                sim_date=rec.day,
            )
            row: dict[str, Any] = {
                "day_index": day_index,
                "date": rec.day.isoformat(),
                "tmin_c": float(rec.tmin_c),
                "tmax_c": float(rec.tmax_c),
                "rain_mm": rain,
                "irrigation_mm": irrigation,
                "shortwave_mj_m2": shortwave,
            }
            row.update(read_state(orch, soil))
            row.update(collector.today)
            row.update(_limitation_row(collector.nutrient_stress, row["water_stress"]))
            daily.append(row)
    except Exception as exc:  # every engine failure is itself a finding
        status = "error"
        error = f"{type(exc).__name__}: {exc} @ day {day_index}"
        tb_tail = "".join(traceback.format_exception(exc)[-8:])

    runtime_s = time.perf_counter() - t0
    scalars = compute_scalars(
        spec, soil, crop, daily, collector, start, status, error, runtime_s
    )
    return RunResult(
        spec=spec,
        soil=soil,
        status=status,
        error=error,
        traceback_tail=tb_tail,
        runtime_s=runtime_s,
        scalars=scalars,
        daily=daily,
    )


# ---------------------------------------------------------------------------
# Season scalars
# ---------------------------------------------------------------------------

# Stress-scenario metrics expressed relative to the normal-weather run of the
# same crop, soil, climate and seed: (metric, minimum reference value below
# which the ratio is meaningless and left NaN).
REL_METRICS: tuple[tuple[str, float], ...] = (
    ("rain_mm", 1.0),
    ("agb_g_m2", 1.0),
    ("grain_g_m2", 20.0),
    ("et0_mm", 1.0),
    ("et_actual_mm", 1.0),
    ("water_stress_days", 5.0),
    ("deep_perc_mm", 10.0),
    ("no3_leached_kg_ha", 5.0),
    ("runoff_mm", 2.0),
    ("som_min_n_kg_ha", 1.0),
    ("denitrification_kg_ha", 1.0),
    ("plant_n_kg_ha", 1.0),
    ("heat_events", 1.0),
    ("co2_c_kg_ha", 1.0),
    ("volatilization_kg_ha", 1.0),
    ("days_any_saturated", 1.0),
    ("day_maturity", 1.0),
)
REL_EXTRA: tuple[str, ...] = (
    "grain_minus_agb_rel",
    "harvest_index_delta",
    "day_maturity_delta",
    "hot_maturity_lost",
    "ref_agb_g_m2",
    "ref_grain_g_m2",
    "ref_day_maturity",
)
REL_COLUMNS: tuple[str, ...] = (*(f"{m}_rel" for m, _ in REL_METRICS), *REL_EXTRA)


def _col(daily: Sequence[dict[str, Any]], key: str) -> list[float]:
    return [float(row[key]) for row in daily]


def _sum(daily: Sequence[dict[str, Any]], key: str) -> float:
    return float(sum(row[key] for row in daily))


def _argmax(values: Sequence[float]) -> tuple[float, int]:
    if not values:
        return math.nan, NOT_REACHED
    best = max(range(len(values)), key=values.__getitem__)
    return values[best], best


def _div(num: float, den: float) -> float:
    return num / den if den else math.nan


def _decrease_days(values: Sequence[float], eps: float = 1e-6) -> int:
    return sum(1 for a, b in pairwise(values) if b < a - eps)


def compute_scalars(
    spec: RunSpec,
    soil: SoilInfo,
    crop: Any,
    daily: list[dict[str, Any]],
    collector: FluxCollector,
    start: dict[str, Any],
    status: str,
    error: str,
    runtime_s: float,
) -> dict[str, Any]:
    scalars: dict[str, Any] = {
        "run_id": spec.run_id,
        "crop": spec.crop,
        "soil": spec.soil,
        "soil_class": soil.soil_class,
        "drainage": soil.drainage,
        "soil_home": soil.home_climate,
        "climate": spec.climate,
        "scenario": spec.scenario,
        "seed": spec.seed,
        "sowing_date": spec.sowing_date.isoformat(),
        "days": spec.days,
        "days_run": len(daily),
        "fit": spec.fit,
        "status": status,
        "error": error,
        "runtime_s": round(runtime_s, 3),
    }
    scalars.update(dict.fromkeys(REL_COLUMNS, math.nan))
    if not start:
        # The orchestrator could not even be read before the first day.
        scalars["exception_day"] = NOT_REACHED
        return scalars
    scalars.update(_plant_scalars(soil, crop, daily, collector, start))
    scalars.update(_limitation_scalars(daily, start))
    scalars.update(_water_scalars(soil, daily, collector, start))
    scalars.update(_nitrogen_scalars(spec, daily, collector, start))
    scalars.update(_som_scalars(daily, collector, start))
    scalars.update(_sanity_scalars(soil, crop, daily, collector, start, status))
    return scalars


def _plant_scalars(
    soil: SoilInfo,
    crop: Any,
    daily: list[dict[str, Any]],
    collector: FluxCollector,
    start: dict[str, Any],
) -> dict[str, Any]:
    final = daily[-1] if daily else start
    peak_lai, peak_lai_day = _argmax(_col(daily, "lai"))
    agb_end = float(final["agb_g_m2"])
    grain_end = float(final["grain_g_m2"])
    hi_max = float(crop.canopy.hi_max)
    stage_days = collector.stage_days
    day_flowering = stage_days.get("FLOWERING", NOT_REACHED)
    active = [row for row in daily if row["lai"] > ACTIVE_LAI]
    harvest_index = _div(grain_end, agb_end) if agb_end > 0 else 0.0
    root_biomass = float(final["root_biomass_g_m2"])
    root_depth = float(final["root_depth_cm"])
    max_depth = float(crop.roots.max_depth_cm)
    return {
        "agb_g_m2": agb_end,
        "grain_g_m2": grain_end,
        "yield_t_ha": grain_end / 100.0,
        "harvest_index": harvest_index,
        "hi_over_hi_max": _div(harvest_index, hi_max) if hi_max > 0 else 0.0,
        "stem_g_m2": float(final["stem_g_m2"]),
        "peak_lai": peak_lai,
        "peak_lai_day": peak_lai_day,
        "final_lai": float(final["lai"]),
        "final_stage": str(final["stage"]),
        "reached_maturity": int(final["stage"] == "MATURITY"),
        "flowered": int(day_flowering != NOT_REACHED),
        "day_emerged": stage_days.get("EMERGED", NOT_REACHED),
        "day_vegetative": stage_days.get("VEGETATIVE", NOT_REACHED),
        "day_flowering": day_flowering,
        "day_grain_fill": stage_days.get("GRAIN_FILL", NOT_REACHED),
        "day_maturity": stage_days.get("MATURITY", NOT_REACHED),
        "gdd_total": float(final["gdd"]),
        "vernalization_units": float(final["vernalization_units"]),
        "root_depth_cm": root_depth,
        "root_biomass_g_m2": root_biomass,
        "root_shoot_ratio": _div(root_biomass, agb_end) if agb_end > 0 else math.nan,
        "root_depth_over_max": _div(root_depth, max_depth),
        "root_depth_over_profile": _div(root_depth, soil.profile_depth_cm),
        "plant_n_kg_ha": float(final["plant_n_kg_ha"]),
        "plant_n_pct": float(final["plant_n_pct"]),
        "nni_final": float(final["nni"]),
        "nni_min": min(r["nni"] for r in active) if active else math.nan,
        "n_stress_days": sum(1 for r in active if r["n_stress"] < 0.5),
        "n_stress_frac": _div(
            sum(1 for r in active if r["n_stress"] < 0.5), len(daily)
        ),
        "water_stress_days": sum(1 for r in active if r["water_stress"] < 0.5),
        "water_stress_mean": (
            sum(1.0 - r["water_stress"] for r in active) / len(active)
            if active
            else 0.0
        ),
        "frost_events": _sum(daily, "frost_events"),
        "heat_events": _sum(daily, "heat_events"),
        "drought_senescence_events": _sum(daily, "drought_senescence_events"),
        "frost_biomass_loss_g_m2": _sum(daily, "frost_biomass_loss_g_m2"),
        "hi_max": hi_max,
        "lai_max": float(crop.canopy.lai_max),
        "max_depth_cm": max_depth,
        "profile_depth_cm": soil.profile_depth_cm,
    }


def _limitation_scalars(
    daily: list[dict[str, Any]], start: dict[str, Any]
) -> dict[str, Any]:
    """What limited canopy growth over the season, and the topsoil redox state
    and micronutrient levels behind it.
    """
    if not daily:
        return {}
    days = len(daily)
    out: dict[str, Any] = {}
    binding_days: dict[str, int] = {}
    for factor in LIMITING_FACTORS:
        key = factor.lower()
        out[f"stress_{key}_mean"] = _sum(daily, f"stress_{key}") / days
        binding_days[key] = sum(1 for r in daily if r["binding_factor"] == key)
        out[f"binding_days_{key}"] = binding_days[key]
    dominant = max(binding_days, key=binding_days.__getitem__)
    out["binding_factor"] = dominant if binding_days[dominant] > 0 else "none"
    out["binding_factor_days"] = binding_days[dominant]
    out["growth_factor_mean"] = _sum(daily, "growth_factor") / days
    eh = _col(daily, "eh_0_mv")
    fe = _col(daily, "fe_avail_0_ppm")
    s_avail = _col(daily, "s_avail_kg_ha")
    out["topsoil_eh_min_mv"] = min(eh)
    out["topsoil_eh_below_100_days"] = sum(1 for v in eh if v < 100.0)
    out["topsoil_anoxic_days"] = sum(
        1 for v in _col(daily, "o2_0_frac") if v < ANOXIC_O2_FRAC
    )
    co2 = _col(daily, "co2_0_frac")
    out["co2_0_median_frac"] = statistics.median(co2)
    out["co2_0_max_frac"] = max(co2)
    out["anaerobic_layer_days"] = _sum(daily, "anaerobic_layers")
    out["fe_avail_0_start_ppm"] = float(start["fe_avail_0_ppm"])
    out["fe_avail_0_max_ppm"] = max(fe)
    out["fe_toxic_days"] = sum(1 for v in fe if v > TOXIC_FE_PPM)
    out["fe_deficient_days"] = sum(1 for v in fe if v < CRITICAL_FE_PPM)
    out["zn_deficient_days"] = sum(
        1 for v in _col(daily, "zn_avail_0_ppm") if v < CRITICAL_ZN_PPM
    )
    out["s_avail_start_kg_ha"] = float(start["s_avail_kg_ha"])
    out["s_avail_min_kg_ha"] = min(s_avail)
    out["s_avail_end_kg_ha"] = s_avail[-1]
    out["so4_leached_kg_ha"] = _sum(daily, "so4_leached_kg_ha")
    return out


def _water_scalars(
    soil: SoilInfo,
    daily: list[dict[str, Any]],
    collector: FluxCollector,
    start: dict[str, Any],
) -> dict[str, Any]:
    final = daily[-1] if daily else start
    days = len(daily)
    rain = _sum(daily, "rain_mm")
    irrigation = _sum(daily, "irrigation_mm")
    et0 = _sum(daily, "et0_mm")
    evap_event = _sum(daily, "evap_mm")
    transp_event = _sum(daily, "transp_mm")
    evap_taken = _sum(daily, "evap_taken_mm")
    transp_taken = _sum(daily, "transp_taken_mm")
    intercept = _sum(daily, "intercept_mm")
    runoff = _sum(daily, "runoff_mm")
    deep_perc = _sum(daily, "deep_perc_mm")
    # The water module's own extraction events are the balance terms; the
    # ET event pair is the fallback when those never fired.
    extraction_seen = evap_taken + transp_taken > 0
    evap = evap_taken if extraction_seen else evap_event
    transp = transp_taken if extraction_seen else transp_event
    et_actual = evap + transp
    storage_start = float(start["storage_mm"])
    storage_end = float(final["storage_mm"])
    residual = (
        rain
        + irrigation
        - et_actual
        - intercept
        - runoff
        - deep_perc
        - (storage_end - storage_start)
    )
    curve_number = (
        collector.curve_number
        if not math.isnan(collector.curve_number)
        else soil.curve_number_default
    )
    n_layers = len(soil.depths_cm)
    wp, sat = soil.wilting_point, soil.saturation

    def saturated(row: dict[str, Any]) -> bool:
        return any(row[f"theta_{j}"] >= sat[j] - 1e-6 for j in range(n_layers))

    def out_of_bounds(row: dict[str, Any]) -> bool:
        return any(
            row[f"theta_{j}"] < wp[j] - 1e-6 or row[f"theta_{j}"] > sat[j] + 1e-9
            for j in range(n_layers)
        )

    theta_top = _col(daily, "theta_0")
    days_any_saturated = sum(1 for r in daily if saturated(r))
    pawc = soil.pawc_mm
    return {
        "rain_mm": rain,
        "irrigation_mm": irrigation,
        "et0_mm": et0,
        "et0_mean_mm_d": _div(et0, days),
        "evap_mm": evap,
        "transp_mm": transp,
        "evap_event_mm": evap_event,
        "transp_event_mm": transp_event,
        "intercept_mm": intercept,
        "canopy_evap_mm": _sum(daily, "canopy_evap_mm"),
        "et_actual_mm": et_actual,
        "et_event_gap_mm": (evap_event + transp_event) - et_actual,
        "et_minus_et0_mm": et_actual - et0,
        "runoff_mm": runoff,
        "deep_perc_mm": deep_perc,
        "storage_start_mm": storage_start,
        "storage_end_mm": storage_end,
        "water_residual_mm": residual,
        "et_over_et0": _div(et_actual, et0),
        "t_over_et": _div(transp, et_actual),
        "runoff_frac": _div(runoff, rain),
        "curve_number": curve_number,
        "pawc_mm": pawc,
        "theta_top_min": min(theta_top) if theta_top else math.nan,
        "theta_top_max": max(theta_top) if theta_top else math.nan,
        "days_theta_below_wp": sum(1 for r in daily if r["theta_0"] <= wp[0] + 1e-6),
        "days_any_saturated": days_any_saturated,
        "saturated_frac": _div(days_any_saturated, days),
        "theta_bound_violation_days": sum(1 for r in daily if out_of_bounds(r)),
        "paw_frac_end": _div(storage_end - soil.wp_storage_mm, pawc),
    }


def _nitrogen_scalars(
    spec: RunSpec,
    daily: list[dict[str, Any]],
    collector: FluxCollector,
    start: dict[str, Any],
) -> dict[str, Any]:
    final = daily[-1] if daily else start
    days = len(daily)
    no3_start, nh4_start = float(start["no3_kg_ha"]), float(start["nh4_kg_ha"])
    no3_end, nh4_end = float(final["no3_kg_ha"]), float(final["nh4_kg_ha"])
    fert = spec.management.fertilizer_kg
    som_min_n = _sum(daily, "som_min_n_kg_ha")
    denit = _sum(daily, "denitrification_kg_ha")
    volat = _sum(daily, "volatilization_kg_ha")
    no3_leached = _sum(daily, "no3_leached_kg_ha")
    nh4_leached = _sum(daily, "nh4_leached_kg_ha")
    uptake = _sum(daily, "n_uptake_kg_ha")
    massflow = _sum(daily, "n_massflow_supply_kg_ha")
    mineral = [float(r["no3_kg_ha"] + r["nh4_kg_ha"]) for r in daily]
    peak, peak_day = _argmax(mineral)
    min_after_peak = min(mineral[peak_day:]) if mineral else math.nan
    delta_mineral = (no3_end + nh4_end) - (no3_start + nh4_start)
    # Nitrification moves N between the two mineral pools and N2O is a
    # partition of denitrification, so neither is a ledger term; mass flow is
    # a potential supply that debits nothing.
    explained = som_min_n + fert - uptake - denit - volat - no3_leached - nh4_leached
    residual = delta_mineral - explained
    gross_supply = som_min_n + fert + no3_start + nh4_start
    first30 = sum(r["som_min_n_kg_ha"] for r in daily[:30])
    first45 = sum(r["som_min_n_kg_ha"] for r in daily[:45])
    last30 = sum(r["som_min_n_kg_ha"] for r in daily[-30:])
    plant_n_gain = float(final["plant_n_kg_ha"]) - float(start["plant_n_kg_ha"])
    return {
        "no3_start_kg_ha": no3_start,
        "nh4_start_kg_ha": nh4_start,
        "no3_end_kg_ha": no3_end,
        "nh4_end_kg_ha": nh4_end,
        "fert_n_kg_ha": fert,
        "som_min_n_kg_ha": som_min_n,
        "nitrification_kg_ha": _sum(daily, "nitrification_kg_ha"),
        "denitrification_kg_ha": denit,
        "volatilization_kg_ha": volat,
        "no3_leached_kg_ha": no3_leached,
        "nh4_leached_kg_ha": nh4_leached,
        "n_uptake_kg_ha": uptake,
        "n_massflow_supply_kg_ha": massflow,
        "n_massflow_supply_over_uptake": _div(massflow, uptake),
        "n_uptake_minus_plant_n_kg_ha": uptake - plant_n_gain,
        "n2o_kg_n_ha": _sum(daily, "n2o_kg_n_ha"),
        "mineral_n_start_kg_ha": no3_start + nh4_start,
        "mineral_n_peak_kg_ha": peak,
        "mineral_n_peak_day": peak_day,
        "mineral_n_min_after_peak_kg_ha": min_after_peak,
        "mineral_n_drawdown": _div(min_after_peak, peak),
        "mineral_n_end_kg_ha": no3_end + nh4_end,
        "som_min_n_first30_rate": _div(first30, min(30, days)),
        "som_min_n_first45_frac": _div(first45, som_min_n),
        "som_min_n_last30_over_first30": _div(last30, first30),
        "n_mineral_residual_kg_ha": residual,
        "n_mineral_residual_pct": _div(100.0 * residual, gross_supply),
    }


def _som_scalars(
    daily: list[dict[str, Any]],
    collector: FluxCollector,
    start: dict[str, Any],
) -> dict[str, Any]:
    final = daily[-1] if daily else start
    som_c_start, som_c_end = float(start["som_c_kg_ha"]), float(final["som_c_kg_ha"])
    som_n_start, som_n_end = float(start["som_n_kg_ha"]), float(final["som_n_kg_ha"])
    co2 = _sum(daily, "co2_c_kg_ha")
    som_min_n = _sum(daily, "som_min_n_kg_ha")
    mic_start = float(start["microbial_c_kg_ha"])
    mic_end = float(final["microbial_c_kg_ha"])
    ph_start, ph_end = float(start["ph_0"]), float(final["ph_0"])
    return {
        "som_c_start_kg_ha": som_c_start,
        "som_c_end_kg_ha": som_c_end,
        "som_c_change_pct": _div(100.0 * (som_c_end - som_c_start), som_c_start),
        # Carbon entering the pools over the season: change plus respiration.
        "som_c_input_kg_ha": (som_c_end - som_c_start) + co2,
        "som_n_start_kg_ha": som_n_start,
        "som_n_end_kg_ha": som_n_end,
        "som_n_change_kg_ha": som_n_end - som_n_start,
        "som_n_input_kg_ha": (som_n_end - som_n_start) + som_min_n,
        "co2_c_kg_ha": co2,
        "som_dec_c_kg_ha": _sum(daily, "som_dec_c_kg_ha"),
        "som_min_n_over_som_n": _div(som_min_n, som_n_start),
        "microbial_c_start_kg_ha": mic_start,
        "microbial_c_end_kg_ha": mic_end,
        "microbial_c_ratio": _div(mic_end, mic_start),
        "microbial_c_over_som_c": _div(mic_start, som_c_start),
        "ph_top_start": ph_start,
        "ph_top_end": ph_end,
        "ph_top_drift": ph_end - ph_start,
    }


def _sanity_scalars(
    soil: SoilInfo,
    crop: Any,
    daily: list[dict[str, Any]],
    collector: FluxCollector,
    start: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    n_layers = len(soil.depths_cm)
    theta_keys = [f"theta_{j}" for j in range(n_layers)]
    pool_keys = [
        "no3_kg_ha",
        "nh4_kg_ha",
        "som_c_kg_ha",
        "lai",
        "agb_g_m2",
        "grain_g_m2",
        "root_biomass_g_m2",
        "microbial_c_kg_ha",
        *theta_keys,
    ]
    flux_keys = (
        "runoff_mm",
        "deep_perc_mm",
        "evap_taken_mm",
        "transp_taken_mm",
        "no3_leached_kg_ha",
        "denitrification_kg_ha",
        "som_min_n_kg_ha",
        "n_uptake_kg_ha",
    )
    numeric_keys = [k for k, v in start.items() if isinstance(v, float)]
    numeric_keys.extend(DAILY_FLUX_KEYS)
    nan_count = sum(
        1
        for r in daily
        for k in numeric_keys
        if isinstance(r[k], float) and math.isnan(r[k])
    )
    agb = [float(start["agb_g_m2"]), *_col(daily, "agb_g_m2")]
    grain = [float(start["grain_g_m2"]), *_col(daily, "grain_g_m2")]
    damage_days = {
        i
        for i, r in enumerate(daily)
        if r["frost_events"] or r["heat_events"] or r["drought_senescence_events"]
    }
    agb_unexplained = sum(
        1
        for i in range(len(daily))
        if agb[i + 1] < agb[i] - 1e-6 and i not in damage_days
    )
    grain_unexplained = sum(
        1
        for i in range(len(daily))
        if grain[i + 1] < grain[i] - 1e-6 and i not in damage_days
    )
    hi_max = float(crop.canopy.hi_max)
    lai_max = float(crop.canopy.lai_max)
    day_maturity = collector.stage_days.get("MATURITY", NOT_REACHED)
    if daily and 0 <= day_maturity < len(daily):
        agb_after_maturity = daily[-1]["agb_g_m2"] - daily[day_maturity]["agb_g_m2"]
    else:
        agb_after_maturity = math.nan
    all_theta = [r[k] for r in daily for k in theta_keys]
    return {
        "nan_count": nan_count,
        "negative_pool_count": sum(
            1 for r in daily if any(r[k] < -1e-9 for k in pool_keys)
        ),
        "negative_flux_count": sum(
            1 for r in daily if any(r[k] < -1e-9 for k in flux_keys)
        ),
        "min_theta": min(all_theta) if all_theta else math.nan,
        "min_no3": min(_col(daily, "no3_kg_ha")) if daily else math.nan,
        "min_nh4": min(_col(daily, "nh4_kg_ha")) if daily else math.nan,
        "min_som_c": min(_col(daily, "som_c_kg_ha")) if daily else math.nan,
        "agb_decrease_days": _decrease_days(agb),
        "agb_decrease_unexplained_days": agb_unexplained,
        "grain_decrease_days": _decrease_days(grain),
        "grain_decrease_unexplained_days": grain_unexplained,
        "root_depth_decrease_days": _decrease_days(
            [float(start["root_depth_cm"]), *_col(daily, "root_depth_cm")]
        ),
        "agb_inc_after_maturity_g_m2": agb_after_maturity,
        "hi_cap_violation_days": sum(
            1 for r in daily if r["grain_g_m2"] > hi_max * r["agb_g_m2"] + 1e-6
        ),
        "lai_cap_violation_days": sum(1 for r in daily if r["lai"] > lai_max + 1e-6),
        "exception_day": len(daily) if status == "error" else NOT_REACHED,
    }


# ---------------------------------------------------------------------------
# Checks: declarative bands over season scalars
# ---------------------------------------------------------------------------

INF = math.inf
Pred = Callable[[dict[str, Any]], bool]
CLIMATE_SHORT = {NL: "nl", KENYA: "kenya", SAHEL: "sahel"}


def _all(scalars: dict[str, Any]) -> bool:
    return True


def _and(*preds: Pred) -> Pred:
    def pred(scalars: dict[str, Any]) -> bool:
        return all(p(scalars) for p in preds)

    return pred


def _or(*preds: Pred) -> Pred:
    def pred(scalars: dict[str, Any]) -> bool:
        return any(p(scalars) for p in preds)

    return pred


def _not(inner: Pred) -> Pred:
    def pred(scalars: dict[str, Any]) -> bool:
        return not inner(scalars)

    return pred


def _in(key: str, *values: Any) -> Pred:
    def pred(scalars: dict[str, Any]) -> bool:
        return scalars.get(key) in values

    return pred


def _ge(key: str, threshold: float) -> Pred:
    def pred(scalars: dict[str, Any]) -> bool:
        value = scalars.get(key)
        return isinstance(value, int | float) and value >= threshold

    return pred


def _lt(key: str, threshold: float) -> Pred:
    def pred(scalars: dict[str, Any]) -> bool:
        value = scalars.get(key)
        return isinstance(value, int | float) and value < threshold

    return pred


def _clim(*values: str) -> Pred:
    return _in("climate", *values)


def _crop(*values: str) -> Pred:
    return _in("crop", *values)


def _soil(*values: str) -> Pred:
    return _in("soil", *values)


def _soil_class(*values: str) -> Pred:
    return _in("soil_class", *values)


def _drainage(*values: str) -> Pred:
    return _in("drainage", *values)


def _scenario(*values: str) -> Pred:
    return _in("scenario", *values)


NORMAL = _scenario("normal")
VIABLE = _not(_in("fit", "not_grown"))
MINERAL = _not(_soil_class("PEAT"))
PEAT = _soil_class("PEAT")
LOW_SOM = _lt("som_c_start_kg_ha", LOW_SOM_C_KG_HA)
NOT_LOW_SOM = _not(LOW_SOM)
# The one preset whose low DTPA-Fe stands for lime-induced chlorosis rather than
# an unset field (data/soils/presets.yaml header).
CALCAREOUS = _soil("sandy_arid")
REACHED = _in("reached_maturity", 1)
FLOWERED = _in("flowered", 1)
NL_SPRING = _and(_clim(NL), _not(_crop("winter_wheat")))
NL_AUTUMN = _and(_clim(NL), _crop("winter_wheat"))
ANCHOR_ROW = _and(NORMAL, _soil("loam_temperate"), _in("seed", DEFAULT_SEED))


@dataclass(frozen=True)
class Check:
    """A band on one season scalar.

    A value outside ``fail`` is a FAIL, outside ``warn`` a WARN; a missing or
    NaN metric is skipped. ``expect`` compares for equality instead and
    reports ``expect_severity`` on mismatch. ``info`` records the value
    without judging it. ``known`` names a documented model limitation so the
    report can separate it from new findings. ``cap_off_home`` downgrades a
    FAIL to WARN when the soil preset is exercised outside the climate it
    was calibrated for.
    """

    name: str
    metric: str
    warn: tuple[float, float] | None = None
    fail: tuple[float, float] | None = None
    applies: Pred = _all
    category: str = "plant"
    source: str = ""
    known: str = ""
    info: bool = False
    cap_off_home: bool = False
    expect: Any = None
    expect_severity: str = "FAIL"


@dataclass(frozen=True)
class Finding:
    run_id: str
    scope: str
    check: str
    category: str
    metric: str
    value: Any
    band: str
    severity: str
    source: str = ""
    known: str = ""
    detail: str = ""
    distance: float = 0.0


def _fmt_num(value: Any) -> str:
    if isinstance(value, float):
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return (
            f"{value:.4g}" if abs(value) < 1e-3 or abs(value) >= 1e4 else f"{value:.3f}"
        )
    return str(value)


def _fmt_interval(band: tuple[float, float]) -> str:
    lo, hi = band
    if math.isinf(lo) and not math.isinf(hi):
        return f"<= {_fmt_num(hi)}"
    if math.isinf(hi) and not math.isinf(lo):
        return f">= {_fmt_num(lo)}"
    if lo == hi:
        return f"== {_fmt_num(lo)}"
    return f"[{_fmt_num(lo)}, {_fmt_num(hi)}]"


def _fmt_band(check: Check) -> str:
    if check.expect is not None:
        return f"== {check.expect}"
    parts = []
    if check.warn is not None:
        parts.append(f"warn {_fmt_interval(check.warn)}")
    if check.fail is not None:
        parts.append(f"fail {_fmt_interval(check.fail)}")
    return "; ".join(parts) if parts else "info"


def _outside(value: float, band: tuple[float, float] | None) -> float:
    """Distance by which ``value`` lies outside ``band`` (0 when inside)."""
    if band is None:
        return 0.0
    lo, hi = band
    if value < lo:
        return lo - value
    if value > hi:
        return value - hi
    return 0.0


def evaluate_check(check: Check, scalars: dict[str, Any]) -> Finding | None:
    if not check.applies(scalars):
        return None
    value = scalars.get(check.metric)
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    common = {
        "run_id": scalars["run_id"],
        "scope": "run",
        "check": check.name,
        "category": check.category,
        "metric": check.metric,
        "value": value,
        "band": _fmt_band(check),
        "source": check.source,
        "known": check.known,
    }
    if check.expect is not None:
        if value == check.expect:
            return None
        return Finding(severity=check.expect_severity, distance=1.0, **common)
    if check.info:
        return Finding(severity="INFO", **common)
    if not isinstance(value, int | float):
        return None
    fail_distance = _outside(float(value), check.fail)
    warn_distance = _outside(float(value), check.warn)
    if fail_distance > 0:
        severity = "FAIL"
        detail = ""
        if check.cap_off_home and scalars.get("soil_home") != scalars.get("climate"):
            severity = "WARN"
            detail = "capped to WARN: soil preset outside its home climate"
        return Finding(
            severity=severity, distance=fail_distance, detail=detail, **common
        )
    if warn_distance > 0:
        return Finding(severity="WARN", distance=warn_distance, **common)
    return None


# --- invariants ------------------------------------------------------------

INVARIANTS: list[Check] = [
    Check(
        "water_balance_closes",
        "water_residual_mm",
        fail=(-0.5, 0.5),
        category="invariant",
        source="rain + irrigation = E + T + interception + runoff + deep percolation "
        "+ dS",
    ),
    Check(
        "mineral_n_ledger_closes",
        "n_mineral_residual_pct",
        warn=(-1.0, 1.0),
        fail=(-5.0, 5.0),
        category="invariant",
        source="dMineralN = mineralisation + fertiliser - uptake - mass flow - "
        "denitrification - volatilisation - leaching",
    ),
    Check("no_nan", "nan_count", fail=(0, 0), category="invariant"),
    Check(
        "no_negative_pools", "negative_pool_count", fail=(0, 0), category="invariant"
    ),
    Check(
        "no_negative_fluxes", "negative_flux_count", fail=(0, 0), category="invariant"
    ),
    Check(
        "theta_within_wp_sat",
        "theta_bound_violation_days",
        fail=(0, 0),
        category="invariant",
        source="soil water content must stay between wilting point and saturation",
    ),
    Check(
        "agb_only_drops_on_damage_events",
        "agb_decrease_unexplained_days",
        fail=(0, 0),
        category="invariant",
        source="above-ground biomass falls only through frost, heat or drought "
        "senescence",
    ),
    Check(
        "grain_only_drops_on_damage_events",
        "grain_decrease_unexplained_days",
        fail=(0, 0),
        category="invariant",
    ),
    Check(
        "root_depth_never_decreases",
        "root_depth_decrease_days",
        fail=(0, 0),
        category="invariant",
    ),
    Check(
        "no_growth_after_maturity",
        "agb_inc_after_maturity_g_m2",
        fail=(-INF, 1.0),
        applies=REACHED,
        category="invariant",
    ),
    Check(
        "grain_within_hi_cap",
        "hi_cap_violation_days",
        fail=(0, 0),
        category="invariant",
    ),
    Check(
        "harvest_index_within_hi_max",
        "hi_over_hi_max",
        fail=(0.0, 1.000001),
        category="invariant",
    ),
    Check(
        "lai_within_lai_max",
        "lai_cap_violation_days",
        fail=(0, 0),
        category="invariant",
    ),
    Check(
        "root_depth_within_crop_max",
        "root_depth_over_max",
        fail=(0.0, 1.000001),
        category="invariant",
    ),
    Check(
        "root_depth_within_profile",
        "root_depth_over_profile",
        warn=(0.0, 1.000001),
        category="invariant",
        source="roots below the simulated profile take up nothing",
    ),
    Check(
        "et_actual_not_above_et0",
        "et_minus_et0_mm",
        fail=(-INF, 0.5),
        category="invariant",
        source="actual ET cannot exceed reference ET for a well-watered surface",
    ),
    Check(
        "grape_no_grain",
        "grain_g_m2",
        fail=(0.0, 0.0),
        applies=_crop("grape"),
        category="invariant",
        source="grape preset has no grain organ",
        known="grape harvest index 0: fruit is not simulated",
    ),
    Check(
        "ph_top_stable",
        "ph_top_drift",
        warn=(-0.5, 0.5),
        fail=(-1.5, 1.5),
        category="invariant",
        source="one season of unfertilised cropping shifts topsoil pH by tenths at "
        "most",
    ),
    Check(
        "microbial_c_stable",
        "microbial_c_ratio",
        warn=(0.5, 2.0),
        fail=(0.1, 5.0),
        category="invariant",
    ),
    Check(
        "uptake_matches_plant_n",
        "n_uptake_minus_plant_n_kg_ha",
        warn=(-0.5, 0.5),
        category="invariant",
        source="tracked uptake events must equal the plant N stock gain",
    ),
]


# --- crop x climate bands ---------------------------------------------------


@dataclass(frozen=True)
class CropBand:
    crop: str
    climate: str
    agb_warn: tuple[float, float] | None = None
    agb_fail: tuple[float, float] | None = None
    grain_warn: tuple[float, float] | None = None
    grain_fail: tuple[float, float] | None = None
    grain_info: bool = False
    grain_zero: bool = False
    hi_warn: tuple[float, float] | None = None
    hi_fail: tuple[float, float] | None = None
    maturity_required: bool | None = None
    maturity_warn: tuple[float, float] | None = None
    flowering_warn: tuple[float, float] | None = None
    lai_warn: tuple[float, float] | None = None
    must_not_flower: bool = False
    source: str = ""
    known_yield: str = ""
    known_maturity: str = ""


KNOWN_LOW_WHEAT = "unfertilised NL wheat far below literature yields"
KNOWN_SW_MATURITY = "spring wheat in NL matures around day 90"
KNOWN_HI_PINNED = "harvest index pinned at the preset hi_max"
KNOWN_PT_ET0 = "Priestley-Taylor ET0, not FAO-56 calibrated"
KNOWN_DRAINED_DENIT = (
    "drained soils denitrify nothing: the gas profile is read after the "
    "same-day drainage to field capacity, and anaerobic microsites need bulk "
    "soil-air O2 below 4 %"
)
KNOWN_NL_GT_KENYA = "NL maize outyields Kenya highland maize"

CROP_BANDS: list[CropBand] = [
    CropBand(
        "maize",
        NL,
        agb_warn=(900, 2000),
        agb_fail=(400, 2600),
        grain_warn=(200, 900),
        grain_fail=(0, 1300),
        flowering_warn=(70, 110),
        lai_warn=(3, 6),
        source="GYGA NL rain-fed silage/grain maize, 150 d season ends in grain fill",
    ),
    CropBand(
        "maize",
        KENYA,
        agb_warn=(800, 2000),
        agb_fail=(300, 2800),
        grain_warn=(250, 900),
        grain_fail=(50, 1300),
        hi_warn=(0.30, 0.55),
        maturity_required=True,
        maturity_warn=(150, 185),
        flowering_warn=(65, 100),
        lai_warn=(3, 6),
        source="GYGA Kenya highland rain-fed maize 2-4 t/ha unfertilised",
    ),
    CropBand(
        "maize",
        SAHEL,
        agb_warn=(400, 1000),
        agb_fail=(150, 1400),
        grain_warn=(100, 400),
        grain_fail=(20, 650),
        hi_warn=(0.20, 0.45),
        maturity_required=True,
        maturity_warn=(70, 120),
        lai_warn=(1.5, 4.5),
        source="Sahel rain-fed maize 1-2 t/ha, short hot season",
    ),
    CropBand(
        "sorghum",
        SAHEL,
        agb_warn=(500, 1300),
        agb_fail=(200, 1800),
        grain_warn=(100, 450),
        grain_fail=(20, 700),
        hi_warn=(0.20, 0.45),
        maturity_required=True,
        maturity_warn=(70, 130),
        lai_warn=(1.5, 4.5),
        source="Sahel sorghum 0.8-2 t/ha, outyields maize under drought",
    ),
    CropBand(
        "sorghum",
        KENYA,
        agb_warn=(500, 1500),
        agb_fail=(100, 2200),
        grain_info=True,
        source="marginal: highland temperatures limit sorghum development",
    ),
    CropBand(
        "sorghum",
        NL,
        agb_warn=(200, 1400),
        agb_fail=(50, 2000),
        grain_info=True,
        source="marginal: NL sorghum rarely fills grain",
    ),
    CropBand(
        "spring_wheat",
        NL,
        agb_warn=(500, 1600),
        agb_fail=(150, 2200),
        grain_warn=(150, 700),
        grain_fail=(30, 1000),
        hi_warn=(0.30, 0.50),
        maturity_required=True,
        maturity_warn=(100, 140),
        lai_warn=(3, 6),
        source="NL spring wheat 5-7 t/ha fertilised; unfertilised 2-4 t/ha",
        known_yield=KNOWN_LOW_WHEAT,
        known_maturity=KNOWN_SW_MATURITY,
    ),
    CropBand(
        "spring_wheat",
        KENYA,
        agb_warn=(600, 2200),
        agb_fail=(250, 2800),
        grain_warn=(200, 900),
        grain_fail=(50, 1300),
        hi_warn=(0.30, 0.50),
        maturity_required=True,
        maturity_warn=(110, 175),
        lai_warn=(3, 6),
        source="Kenya highland wheat 2-4 t/ha",
    ),
    CropBand(
        "winter_wheat",
        NL,
        agb_warn=(400, 2200),
        agb_fail=(100, 2800),
        grain_warn=(150, 1000),
        grain_fail=(30, 1300),
        hi_warn=(0.35, 0.52),
        maturity_required=True,
        maturity_warn=(240, 280),
        flowering_warn=(215, 250),
        lai_warn=(2, 7),
        source="NL winter wheat 8-10 t/ha fertilised; autumn sowing, July harvest",
        known_yield=KNOWN_LOW_WHEAT,
    ),
    CropBand(
        "winter_wheat",
        KENYA,
        must_not_flower=True,
        grain_zero=True,
        source="no vernalisation in the highland tropics",
    ),
    CropBand(
        "winter_wheat",
        SAHEL,
        agb_warn=(0, 250),
        must_not_flower=True,
        grain_zero=True,
        source="no vernalisation and heat stress in the Sahel",
    ),
    CropBand(
        "rice",
        KENYA,
        agb_warn=(400, 1400),
        agb_fail=(150, 2200),
        grain_warn=(200, 600),
        grain_fail=(30, 900),
        hi_warn=(0.35, 0.50),
        maturity_required=True,
        maturity_warn=(120, 180),
        lai_warn=(2.5, 7),
        source="rain-fed highland rice 2-5 t/ha",
    ),
    CropBand(
        "rice",
        SAHEL,
        agb_warn=(200, 900),
        agb_fail=(0, 1400),
        grain_info=True,
        source="marginal: rain-fed rice in the Sahel is water-limited",
    ),
    CropBand("rice", NL, agb_warn=(0, 600), source="not grown: too cold"),
    CropBand(
        "soybean",
        KENYA,
        agb_warn=(400, 1200),
        agb_fail=(100, 1800),
        grain_warn=(150, 450),
        grain_fail=(30, 700),
        hi_warn=(0.30, 0.45),
        hi_fail=(0.10, 0.50),
        maturity_required=True,
        maturity_warn=(110, 180),
        lai_warn=(2, 5),
        source="East African soybean 1.5-3 t/ha",
    ),
    CropBand(
        "soybean",
        NL,
        agb_warn=(300, 900),
        agb_fail=(50, 1500),
        grain_info=True,
        source="marginal: NL soybean 2-3 t/ha in warm years",
    ),
    CropBand(
        "soybean",
        SAHEL,
        agb_warn=(100, 1000),
        agb_fail=(0, 1500),
        grain_info=True,
        source="marginal: Sahel soybean water-limited",
    ),
    CropBand(
        "grape",
        NL,
        agb_warn=(100, 500),
        agb_fail=(10, 900),
        grain_zero=True,
        lai_warn=(0.5, 4),
        source="vineyard canopy 1-4 t DM/ha/season",
    ),
    CropBand(
        "grape",
        KENYA,
        agb_warn=(50, 600),
        agb_fail=(0, 1000),
        grain_zero=True,
        lai_warn=(0.5, 4),
        source="highland vineyard canopy",
    ),
    CropBand(
        "grape",
        SAHEL,
        agb_warn=(0, 200),
        grain_zero=True,
        source="not grown: heat and drought",
    ),
]


def _expand_crop_band(band: CropBand) -> list[Check]:
    base = _and(NORMAL, _crop(band.crop), _clim(band.climate))
    tag = f"{band.crop}:{CLIMATE_SHORT[band.climate]}"
    checks: list[Check] = []
    if band.agb_warn or band.agb_fail:
        checks.append(
            Check(
                f"agb:{tag}",
                "agb_g_m2",
                band.agb_warn,
                band.agb_fail,
                base,
                "crop",
                band.source,
                band.known_yield,
            )
        )
    if band.grain_info:
        checks.append(
            Check(
                f"grain:{tag}", "grain_g_m2", applies=base, category="crop", info=True
            )
        )
    elif band.grain_zero:
        checks.append(
            Check(
                f"grain_zero:{tag}",
                "grain_g_m2",
                fail=(0.0, 0.0),
                applies=base,
                category="crop",
                source=band.source,
            )
        )
    elif band.grain_warn or band.grain_fail:
        checks.append(
            Check(
                f"grain:{tag}",
                "grain_g_m2",
                band.grain_warn,
                band.grain_fail,
                base,
                "crop",
                band.source,
                band.known_yield,
            )
        )
    if band.hi_warn or band.hi_fail:
        checks.append(
            Check(
                f"harvest_index:{tag}",
                "harvest_index",
                band.hi_warn,
                band.hi_fail,
                _and(base, REACHED),
                "crop",
                band.source,
                "",
            )
        )
    if band.maturity_required is True:
        checks.append(
            Check(
                f"reaches_maturity:{tag}",
                "reached_maturity",
                applies=base,
                category="crop",
                source=band.source,
                known=band.known_maturity,
                expect=1,
                expect_severity="WARN",
            )
        )
    if band.maturity_warn:
        checks.append(
            Check(
                f"day_maturity:{tag}",
                "day_maturity",
                warn=band.maturity_warn,
                applies=_and(base, REACHED),
                category="crop",
                source=band.source,
                known=band.known_maturity,
            )
        )
    if band.flowering_warn:
        checks.append(
            Check(
                f"day_flowering:{tag}",
                "day_flowering",
                warn=band.flowering_warn,
                applies=_and(base, FLOWERED),
                category="crop",
                source=band.source,
            )
        )
    if band.lai_warn:
        checks.append(
            Check(
                f"peak_lai:{tag}",
                "peak_lai",
                warn=band.lai_warn,
                applies=base,
                category="crop",
                source=band.source,
            )
        )
    if band.must_not_flower:
        checks.append(
            Check(
                f"must_not_flower:{tag}",
                "flowered",
                applies=base,
                category="crop",
                source=band.source,
                expect=0,
                expect_severity="FAIL",
            )
        )
    return checks


PLANT_CHECKS: list[Check] = [
    Check(
        "root_depth_reaches_60pct_of_max",
        "root_depth_over_max",
        warn=(0.6, INF),
        applies=_and(NORMAL, VIABLE),
        source="a full-season crop roots to most of its genetic maximum",
    ),
    Check(
        "root_shoot_ratio_cereal",
        "root_shoot_ratio",
        warn=(0.08, 0.40),
        fail=(0.02, 1.0),
        applies=_and(NORMAL, VIABLE, _crop(*CEREALS), _ge("agb_g_m2", 300)),
        source="cereal root:shoot at maturity 0.1-0.3 (Amos & Walters 2006)",
    ),
    Check(
        "root_shoot_ratio_grape",
        "root_shoot_ratio",
        warn=(0.15, 0.7),
        applies=_and(NORMAL, VIABLE, _crop("grape"), _ge("agb_g_m2", 50)),
    ),
    Check(
        "plant_n_stock_humid",
        "plant_n_kg_ha",
        warn=(80, 250),
        fail=(20, 400),
        applies=_and(
            NORMAL, VIABLE, _clim(NL, KENYA), _not(_crop(*WHEATS)), _ge("agb_g_m2", 300)
        ),
        source="unfertilised crop N uptake 80-250 kg N/ha",
    ),
    Check(
        "plant_n_stock_wheat",
        "plant_n_kg_ha",
        warn=(40, 220),
        fail=(20, 400),
        applies=_and(
            NORMAL, VIABLE, _clim(NL, KENYA), _crop(*WHEATS), _ge("agb_g_m2", 300)
        ),
    ),
    Check(
        "plant_n_stock_sahel",
        "plant_n_kg_ha",
        warn=(40, 160),
        fail=(20, 400),
        applies=_and(NORMAL, VIABLE, _clim(SAHEL), _ge("agb_g_m2", 300)),
    ),
    Check(
        "plant_n_concentration",
        "plant_n_pct",
        warn=(0.8, 2.0),
        fail=(0.3, 5.0),
        applies=_and(NORMAL, VIABLE, _ge("agb_g_m2", 300)),
        source="whole-shoot N at maturity 0.8-2 % of dry matter",
    ),
    Check(
        "nni_final",
        "nni_final",
        warn=(0.5, 1.05),
        fail=(0.0, 1.3),
        applies=_and(NORMAL, VIABLE, NOT_LOW_SOM, _ge("agb_g_m2", 300)),
        source="nitrogen nutrition index (Lemaire) 0.5-1.05 for unfertilised crops",
    ),
    Check(
        "nni_final_low_som",
        "nni_final",
        warn=(0.2, 0.9),
        fail=(0.0, 1.3),
        applies=_and(NORMAL, VIABLE, LOW_SOM, _ge("agb_g_m2", 300)),
        source="low-SOM soils leave the crop N-deficient",
    ),
    Check(
        "nni_min",
        "nni_min",
        warn=(0.3, INF),
        applies=_and(NORMAL, VIABLE, _ge("agb_g_m2", 300)),
    ),
    Check(
        "n_stress_fraction",
        "n_stress_frac",
        warn=(0.0, 0.6),
        applies=_and(NORMAL, VIABLE, NOT_LOW_SOM),
        source="N stress on more than 60 % of days is not a fertile-soil outcome",
    ),
    Check(
        "winter_wheat_vernalised",
        "vernalization_units",
        warn=(40, INF),
        applies=_and(NORMAL, _crop("winter_wheat"), _clim(NL)),
        source="autumn-sown wheat accumulates its vernalisation requirement by spring",
    ),
    Check(
        "hi_pinned_at_max_winter_wheat",
        "hi_over_hi_max",
        warn=(0.0, 0.999),
        applies=_and(
            NORMAL, VIABLE, REACHED, _crop("winter_wheat"), _ge("grain_g_m2", 1)
        ),
        known=KNOWN_HI_PINNED,
    ),
    Check(
        "hi_pinned_at_max",
        "hi_over_hi_max",
        warn=(0.0, 0.999),
        applies=_and(
            NORMAL,
            VIABLE,
            REACHED,
            _not(_crop("winter_wheat")),
            _ge("grain_g_m2", 1),
        ),
        source="a harvest index exactly at the genetic cap means grain growth was "
        "clipped",
    ),
]


def _water_checks() -> list[Check]:
    checks: list[Check] = []
    et0_bands = [
        ("nl_spring", NL_SPRING, (2.2, 4.0), (1.0, 7.0)),
        ("nl_autumn", NL_AUTUMN, (1.0, 2.5), (0.3, 5.0)),
        ("kenya", _clim(KENYA), (3.0, 5.0), (1.5, 8.0)),
        ("sahel", _clim(SAHEL), (4.5, 8.5), (3.0, 12.0)),
    ]
    for tag, pred, warn, fail in et0_bands:
        checks.append(
            Check(
                f"et0_mean:{tag}",
                "et0_mean_mm_d",
                warn,
                fail,
                _and(NORMAL, pred),
                "water",
                "FAO-56 climatology of daily reference ET",
                KNOWN_PT_ET0,
            )
        )
    et_bands = [
        ("nl_spring", NL_SPRING, (250, 500), (100, 650)),
        ("nl_autumn", NL_AUTUMN, (300, 600), (100, 800)),
        ("kenya", _clim(KENYA), (400, 800), (150, 1000)),
        ("sahel", _clim(SAHEL), (200, 450), (80, 600)),
    ]
    for tag, pred, warn, fail in et_bands:
        checks.append(
            Check(
                f"et_actual:{tag}",
                "et_actual_mm",
                warn,
                fail,
                _and(NORMAL, VIABLE, pred, _ge("agb_g_m2", 300)),
                "water",
                "seasonal crop evapotranspiration (FAO-56 Kc approach)",
            )
        )
    checks += [
        Check(
            "et_over_et0:humid",
            "et_over_et0",
            warn=(0.55, 1.0),
            fail=(0.2, 1.15),
            applies=_and(NORMAL, VIABLE, _clim(NL, KENYA)),
            category="water",
            source="seasonal ETa/ET0 0.6-1.0 for rain-fed crops in humid climates",
        ),
        Check(
            "et_over_et0:sahel",
            "et_over_et0",
            warn=(0.25, 0.75),
            fail=(0.1, 1.0),
            applies=_and(NORMAL, VIABLE, _clim(SAHEL)),
            category="water",
            source="water-limited Sahel crops evaporate a fraction of ET0",
        ),
        Check(
            "t_over_et:closed_canopy",
            "t_over_et",
            warn=(0.5, 0.85),
            fail=(0.2, 1.0),
            applies=_and(NORMAL, VIABLE, _ge("peak_lai", 3)),
            category="water",
            source="transpiration share of ET 50-85 % under a closed canopy",
        ),
        Check(
            "t_over_et:open_canopy",
            "t_over_et",
            warn=(0.3, 0.7),
            fail=(0.2, 1.0),
            applies=_and(NORMAL, VIABLE, _ge("peak_lai", 1), _lt("peak_lai", 3)),
            category="water",
        ),
        Check(
            "runoff_frac:nl",
            "runoff_frac",
            warn=(0.0, 0.12),
            fail=(0.0, 0.30),
            applies=_and(NORMAL, _clim(NL)),
            category="water",
            source="flat NL cropland sheds little surface runoff",
        ),
        Check(
            "runoff_frac:kenya",
            "runoff_frac",
            warn=(0.02, 0.25),
            fail=(0.0, 0.45),
            applies=_and(NORMAL, _clim(KENYA)),
            category="water",
            source="intense highland rains produce 5-25 % runoff",
        ),
        Check(
            "runoff_frac:sahel_light",
            "runoff_frac",
            warn=(0.0, 0.08),
            fail=(0.0, 0.45),
            applies=_and(NORMAL, _clim(SAHEL), _drainage("LIGHT")),
            category="water",
        ),
        Check(
            "runoff_frac:sahel_other",
            "runoff_frac",
            warn=(0.0, 0.25),
            fail=(0.0, 0.45),
            applies=_and(NORMAL, _clim(SAHEL), _not(_drainage("LIGHT"))),
            category="water",
        ),
        Check(
            "saturation_days:sand",
            "saturated_frac",
            warn=(0.0, 0.3),
            applies=_and(NORMAL, _soil_class("SAND")),
            category="water",
            source="a sand should not sit saturated for a third of the season",
        ),
    ]
    deep_bands = {
        "nl_spring": (
            NL_SPRING,
            {"LIGHT": (0, 200), "MEDIUM": (0, 120), "HEAVY": (0, 80)},
            (0, 350),
        ),
        "nl_autumn": (
            NL_AUTUMN,
            {"LIGHT": (200, 550), "MEDIUM": (150, 450), "HEAVY": (80, 350)},
            (50, 700),
        ),
        "kenya": (
            _clim(KENYA),
            {"LIGHT": (250, 700), "MEDIUM": (100, 500), "HEAVY": (50, 400)},
            (0, 800),
        ),
        "sahel": (
            _clim(SAHEL),
            {"LIGHT": (10, 150), "MEDIUM": (0, 60), "HEAVY": (0, 40)},
            (0, 300),
        ),
    }
    for tag, (pred, by_drainage, fail) in deep_bands.items():
        for drainage, warn in by_drainage.items():
            checks.append(
                Check(
                    f"deep_perc:{tag}:{drainage.lower()}",
                    "deep_perc_mm",
                    warn,
                    fail,
                    _and(NORMAL, pred, _drainage(drainage)),
                    "water",
                    "seasonal drainage below the root zone by texture and rainfall",
                )
            )
    return checks


def _nitrogen_checks() -> list[Check]:
    checks: list[Check] = []
    leach_bands = {
        "nl_spring": (
            NL_SPRING,
            {"LIGHT": ((0, 80), 200), "MEDIUM": ((0, 40), 120), "HEAVY": ((0, 25), 80)},
        ),
        "nl_autumn": (
            NL_AUTUMN,
            {
                "LIGHT": ((20, 150), 300),
                "MEDIUM": ((10, 80), 200),
                "HEAVY": ((5, 60), 150),
            },
        ),
        "kenya": (
            _clim(KENYA),
            {
                "LIGHT": ((5, 250), 400),
                "MEDIUM": ((20, 120), 250),
                "HEAVY": ((10, 80), 200),
            },
        ),
        "sahel": (
            _clim(SAHEL),
            {"LIGHT": ((0, 40), 100), "MEDIUM": ((0, 15), 60), "HEAVY": ((0, 15), 60)},
        ),
    }
    for tag, (pred, by_drainage) in leach_bands.items():
        for drainage, (warn, fail_hi) in by_drainage.items():
            checks.append(
                Check(
                    f"no3_leached:{tag}:{drainage.lower()}",
                    "no3_leached_kg_ha",
                    warn,
                    (0, fail_hi),
                    _and(NORMAL, MINERAL, pred, _drainage(drainage)),
                    "nitrogen",
                    "unfertilised nitrate leaching by texture and rainfall (Di & "
                    "Cameron 2002)",
                )
            )
    checks += [
        Check(
            "no3_leached:peat",
            "no3_leached_kg_ha",
            warn=(20, 200),
            fail=(0, 500),
            applies=_and(NORMAL, PEAT),
            category="nitrogen",
            source="drained peat mineralises and leaches heavily",
        ),
        Check(
            "nh4_leached",
            "nh4_leached_kg_ha",
            warn=(0, 2),
            fail=(0, 10),
            applies=NORMAL,
            category="nitrogen",
            source="ammonium is adsorbed and barely leaches",
        ),
        Check(
            "denitrification:peat",
            "denitrification_kg_ha",
            warn=(1, 80),
            fail=(0, 200),
            applies=_and(NORMAL, PEAT),
            category="nitrogen",
        ),
        Check(
            "denitrification:clay",
            "denitrification_kg_ha",
            warn=(1, 80),
            fail=(0, 200),
            applies=_and(NORMAL, _soil_class("CLAY")),
            category="nitrogen",
            source="wet clays denitrify a few to tens of kg N/ha/season; irrigated "
            "or flooded clays reach the upper end",
        ),
        Check(
            "denitrification:sahel_sand",
            "denitrification_kg_ha",
            warn=(0, 15),
            fail=(0, 50),
            applies=_and(NORMAL, _soil_class("SAND"), _clim(SAHEL)),
            category="nitrogen",
        ),
        Check(
            "denitrification:mineral",
            "denitrification_kg_ha",
            warn=(0.5, 40),
            fail=(0, 100),
            applies=_and(
                NORMAL,
                MINERAL,
                _not(_soil_class("CLAY")),
                _not(_and(_soil_class("SAND"), _clim(SAHEL))),
            ),
            category="nitrogen",
            source="unfertilised mineral soils denitrify 1-40 kg N/ha/season",
            known=KNOWN_DRAINED_DENIT,
        ),
        Check(
            "n2o_emission",
            "n2o_kg_n_ha",
            warn=(0.2, 5),
            fail=(0, 10),
            applies=NORMAL,
            category="nitrogen",
            source="cropland N2O 0.2-5 kg N/ha/yr (IPCC EF1 with background)",
        ),
        Check(
            "volatilisation_unfertilised",
            "volatilization_kg_ha",
            warn=(0, 5),
            fail=(0, 20),
            applies=_and(NORMAL, _in("fert_n_kg_ha", 0.0)),
            category="nitrogen",
            source="without urea or manure NH3 volatilisation is a few kg N/ha at most",
        ),
        Check(
            "massflow_supply_over_uptake",
            "n_massflow_supply_over_uptake",
            applies=_and(NORMAL, VIABLE, _ge("agb_g_m2", 300)),
            category="nitrogen",
            source="potential NO3 carried to the roots by transpiration relative to "
            "demand-driven uptake: above 1 the transpiration stream alone could "
            "supply the crop, below 1 diffusion must contribute",
            info=True,
        ),
        Check(
            "som_min_n_over_som_n",
            "som_min_n_over_som_n",
            warn=(0.004, 0.05),
            fail=(0, 0.10),
            applies=NORMAL,
            category="som",
            source=(
                "1-3 % of organic N mineralises per year in temperate soils, "
                "up to ~5 % over a long warm season (Stanford & Smith 1972)"
            ),
            cap_off_home=True,
        ),
        Check(
            "som_min_n_first30_rate:loam",
            "som_min_n_first30_rate",
            warn=(1, 4),
            applies=_and(NORMAL, _soil_class("LOAM", "CLAY_LOAM")),
            category="som",
            source="net mineralisation 1-4 kg N/ha/d in fertile loams",
            cap_off_home=True,
        ),
        Check(
            "som_min_n_first30_rate:sand",
            "som_min_n_first30_rate",
            warn=(0.2, 2),
            applies=_and(NORMAL, _soil_class("SAND")),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "som_min_n_first30_rate:peat",
            "som_min_n_first30_rate",
            warn=(2, 15),
            applies=_and(NORMAL, PEAT),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "som_min_n_not_front_loaded",
            "som_min_n_last30_over_first30",
            warn=(0.10, INF),
            applies=NORMAL,
            category="som",
            source="mineralisation should not collapse after an initial labile flush",
        ),
        Check(
            "som_min_n_first45_share",
            "som_min_n_first45_frac",
            warn=(0, 0.6),
            applies=NORMAL,
            category="som",
        ),
        Check(
            "mineral_n_drawdown_by_crop",
            "mineral_n_drawdown",
            warn=(0, 0.6),
            applies=_and(NORMAL, VIABLE, _ge("agb_g_m2", 500)),
            category="nitrogen",
            source="a productive crop draws mineral N well below its seasonal peak",
        ),
        Check(
            "mineral_n_end",
            "mineral_n_end_kg_ha",
            warn=(5, 150),
            fail=(0, 400),
            applies=_and(NORMAL, MINERAL),
            category="nitrogen",
            source="residual mineral N after an unfertilised crop 5-150 kg N/ha",
            cap_off_home=True,
        ),
    ]
    som_min_bands = [
        ("low_som", LOW_SOM, (10, 120), 300),
        ("sand", _and(_soil_class("SAND"), NOT_LOW_SOM), (40, 250), 600),
        ("sandy_loam", _soil_class("SANDY_LOAM"), (60, 300), 700),
        ("loam", _soil_class("LOAM"), (80, 350), 900),
        ("clay_loam", _soil_class("CLAY_LOAM"), (90, 400), 1000),
        ("clay", _soil_class("CLAY"), (100, 500), 1200),
        ("peat", PEAT, (150, 1200), 4000),
    ]
    for tag, pred, warn, fail_hi in som_min_bands:
        checks.append(
            Check(
                f"som_min_n:{tag}",
                "som_min_n_kg_ha",
                warn,
                (0, fail_hi),
                _and(NORMAL, pred),
                "som",
                "seasonal net N mineralisation by soil class (unfertilised)",
                cap_off_home=True,
            )
        )
    peak_bands = [
        ("low_som", LOW_SOM, (8, 120), 300),
        ("sand", _and(_soil_class("SAND"), NOT_LOW_SOM), (20, 180), 400),
        ("sandy_loam", _soil_class("SANDY_LOAM"), (30, 200), 450),
        ("loam", _soil_class("LOAM", "CLAY_LOAM"), (40, 220), 450),
        ("clay", _soil_class("CLAY"), (50, 280), 600),
        ("peat", PEAT, (100, 800), 3000),
    ]
    for tag, pred, warn, fail_hi in peak_bands:
        checks.append(
            Check(
                f"mineral_n_peak:{tag}",
                "mineral_n_peak_kg_ha",
                warn,
                (0, fail_hi),
                _and(NORMAL, pred),
                "nitrogen",
                "peak profile mineral N of an unfertilised soil",
                cap_off_home=True,
            )
        )
    return checks


def _som_checks() -> list[Check]:
    checks: list[Check] = [
        Check(
            "som_c_change:mineral",
            "som_c_change_pct",
            warn=(-6, 0.5),
            fail=(-15, 5),
            applies=_and(NORMAL, MINERAL, NOT_LOW_SOM, _not(_crop("winter_wheat"))),
            category="som",
            source="RothC loses 1-3 % of SOC in a fallow season",
            cap_off_home=True,
        ),
        Check(
            "som_c_change:mineral_280d",
            "som_c_change_pct",
            warn=(-8, 0.5),
            fail=(-18, 5),
            applies=_and(NORMAL, MINERAL, NOT_LOW_SOM, _crop("winter_wheat")),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "som_c_change:peat",
            "som_c_change_pct",
            warn=(-4, 0.5),
            fail=(-12, 5),
            applies=_and(NORMAL, PEAT),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "som_c_change:low_som",
            "som_c_change_pct",
            warn=(-10, 1),
            fail=(-25, 5),
            applies=_and(NORMAL, LOW_SOM),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "co2_respiration:nl",
            "co2_c_kg_ha",
            warn=(200, 3000),
            fail=(20, 9000),
            applies=_and(NORMAL, MINERAL, _clim(NL)),
            category="som",
            source="heterotrophic respiration 0.5-3 t C/ha/season in temperate "
            "cropland",
            cap_off_home=True,
        ),
        Check(
            "co2_respiration:kenya",
            "co2_c_kg_ha",
            warn=(300, 5000),
            fail=(20, 9000),
            applies=_and(NORMAL, MINERAL, _clim(KENYA)),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "co2_respiration:sahel",
            "co2_c_kg_ha",
            warn=(100, 2500),
            fail=(20, 9000),
            applies=_and(NORMAL, MINERAL, _clim(SAHEL)),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "co2_respiration:peat",
            "co2_c_kg_ha",
            warn=(1500, 12000),
            fail=(300, 30000),
            applies=_and(NORMAL, PEAT),
            category="som",
            cap_off_home=True,
        ),
        Check(
            "microbial_c_share_of_som",
            "microbial_c_over_som_c",
            warn=(0.005, 0.05),
            fail=(0.0005, 0.15),
            applies=NORMAL,
            category="som",
            source="microbial biomass C is 1-5 % of SOC (Anderson & Domsch 1989)",
        ),
    ]
    return checks


def _stress_checks() -> list[Check]:
    drought = _scenario("drought")
    wet = _scenario("wet")
    hot = _scenario("hot")
    humid = _clim(NL, KENYA)
    sahel = _clim(SAHEL)

    def stress(
        name: str,
        metric: str,
        applies: Pred,
        warn: tuple[float, float] | None = None,
        fail: tuple[float, float] | None = None,
        source: str = "",
    ) -> Check:
        return Check(name, metric, warn, fail, applies, "stress", source)

    return [
        stress("drought:rain_rel", "rain_mm_rel", drought, warn=(0.15, 0.30)),
        stress(
            "drought:agb_rel:sahel",
            "agb_g_m2_rel",
            _and(drought, sahel),
            warn=(0.1, 0.7),
            fail=(0, 1.02),
            source="a fifth of the rain in the Sahel must cut biomass hard",
        ),
        stress(
            "drought:agb_rel:humid",
            "agb_g_m2_rel",
            _and(drought, humid),
            warn=(0.3, 0.95),
            fail=(0, 1.05),
        ),
        stress(
            "drought:grain_falls_at_least_as_much_as_agb",
            "grain_minus_agb_rel",
            drought,
            warn=(-INF, 0.05),
            source="grain is more drought-sensitive than total biomass",
        ),
        stress("drought:grain_rel", "grain_g_m2_rel", drought, fail=(0, 1.05)),
        stress("drought:hi_delta", "harvest_index_delta", drought, warn=(-INF, 0.02)),
        stress(
            "drought:more_water_stress_days",
            "water_stress_days_rel",
            drought,
            fail=(1.0, INF),
        ),
        stress(
            "drought:et_actual_rel",
            "et_actual_mm_rel",
            drought,
            warn=(0.3, 0.95),
            fail=(0, 1.02),
        ),
        stress(
            "drought:deep_perc_rel",
            "deep_perc_mm_rel",
            drought,
            warn=(0, 0.5),
            fail=(0, 1.0),
        ),
        stress(
            "drought:no3_leached_rel",
            "no3_leached_kg_ha_rel",
            drought,
            warn=(0, 0.6),
            fail=(0, 1.1),
        ),
        stress(
            "drought:runoff_rel", "runoff_mm_rel", drought, warn=(0, 0.5), fail=(0, 1.0)
        ),
        stress(
            "drought:earlier_maturity",
            "day_maturity_delta",
            drought,
            warn=(-INF, -3),
            fail=(-INF, 2),
            source="+2 C shortens the thermal-time season",
        ),
        stress(
            "drought:som_min_n_rel", "som_min_n_kg_ha_rel", drought, warn=(0.7, 1.1)
        ),
        stress(
            "drought:denitrification_rel",
            "denitrification_kg_ha_rel",
            drought,
            warn=(0, 1.0),
            fail=(0, 1.5),
            source="denitrification needs wet soil",
        ),
        stress(
            "drought:plant_n_rel",
            "plant_n_kg_ha_rel",
            drought,
            warn=(0, 1.05),
            fail=(0, 1.15),
        ),
        stress("wet:rain_rel", "rain_mm_rel", wet, warn=(1.8, 2.2)),
        stress("wet:et0_rel", "et0_mm_rel", wet, warn=(0.88, 0.95), fail=(0, 1.0)),
        stress(
            "wet:deep_perc_rel",
            "deep_perc_mm_rel",
            wet,
            warn=(1.3, INF),
            fail=(1.0, INF),
        ),
        stress(
            "wet:no3_leached_rel",
            "no3_leached_kg_ha_rel",
            wet,
            warn=(1.2, INF),
            fail=(0.9, INF),
        ),
        stress(
            "wet:runoff_rel", "runoff_mm_rel", wet, warn=(1.5, INF), fail=(1.0, INF)
        ),
        stress(
            "wet:fewer_water_stress_days", "water_stress_days_rel", wet, fail=(0, 1.0)
        ),
        stress(
            "wet:agb_rel:sahel",
            "agb_g_m2_rel",
            _and(wet, sahel),
            warn=(1.05, 2.0),
            fail=(0.9, INF),
            source="doubling Sahel rain relieves the water limitation",
        ),
        stress(
            "wet:agb_rel:humid",
            "agb_g_m2_rel",
            _and(wet, humid),
            warn=(0.8, 1.05),
            fail=(0.6, 1.15),
            source="more rain in a humid climate changes biomass little",
        ),
        stress(
            "wet:denitrification_rel:clay",
            "denitrification_kg_ha_rel",
            _and(wet, _soil_class("CLAY")),
            warn=(1.2, INF),
            fail=(1.0, INF),
        ),
        stress(
            "wet:more_saturated_days", "days_any_saturated_rel", wet, warn=(1.0, INF)
        ),
        stress("hot:et0_rel", "et0_mm_rel", hot, warn=(1.15, 1.40), fail=(1.05, INF)),
        stress(
            "hot:earlier_maturity:nl",
            "day_maturity_rel",
            _and(hot, _clim(NL)),
            warn=(0.55, 0.75),
            fail=(0, 1.0),
            source="+5 C accelerates thermal time most where it is coolest",
        ),
        stress(
            "hot:earlier_maturity:kenya",
            "day_maturity_rel",
            _and(hot, _clim(KENYA)),
            warn=(0.65, 0.85),
            fail=(0, 1.0),
        ),
        stress(
            "hot:earlier_maturity:sahel",
            "day_maturity_rel",
            _and(hot, sahel),
            warn=(0.85, 0.97),
            fail=(0, 1.0),
        ),
        stress("hot:maturity_not_lost", "hot_maturity_lost", hot, fail=(0, 0)),
        stress(
            "hot:agb_rel:sahel_maize",
            "agb_g_m2_rel",
            _and(hot, sahel, _crop("maize")),
            warn=(0.5, 0.95),
            fail=(0, 1.1),
            source="heat above the optimum shortens and stresses Sahel maize",
        ),
        stress(
            "hot:agb_rel:sahel_sorghum",
            "agb_g_m2_rel",
            _and(hot, sahel, _crop("sorghum")),
            warn=(0.7, 1.05),
            fail=(0, 1.1),
        ),
        stress(
            "hot:agb_rel:nl_maize",
            "agb_g_m2_rel",
            _and(hot, _clim(NL), _crop("maize")),
            warn=(0.9, 1.4),
            fail=(0.7, INF),
            source="NL maize is temperature-limited and gains from warmth",
        ),
        stress(
            "hot:agb_rel:nl_wheat",
            "agb_g_m2_rel",
            _and(hot, _clim(NL), _crop("spring_wheat")),
            warn=(0.6, 1.0),
            fail=(0, 1.15),
        ),
        stress(
            "hot:agb_rel:kenya_maize",
            "agb_g_m2_rel",
            _and(hot, _clim(KENYA), _crop("maize")),
            warn=(0.8, 1.2),
            fail=(0.5, INF),
        ),
        stress(
            "hot:agb_rel:kenya_wheat",
            "agb_g_m2_rel",
            _and(hot, _clim(KENYA), _crop("spring_wheat")),
            warn=(0.6, 1.0),
            fail=(0, 1.2),
        ),
        stress(
            "hot:hi_delta:sahel",
            "harvest_index_delta",
            _and(hot, sahel),
            warn=(-INF, 0.02),
        ),
        stress("hot:more_heat_events", "heat_events_rel", hot, fail=(1.0, INF)),
        stress(
            "hot:et_actual_rel:nl",
            "et_actual_mm_rel",
            _and(hot, _clim(NL)),
            warn=(1.0, 1.3),
        ),
        stress(
            "hot:et_actual_rel:sahel",
            "et_actual_mm_rel",
            _and(hot, sahel),
            warn=(0.8, 1.1),
        ),
        stress(
            "hot:som_min_n_rel",
            "som_min_n_kg_ha_rel",
            hot,
            warn=(1.15, 1.6),
            fail=(0.9, INF),
            source="Q10 ~ 2: +5 C raises decomposition 30-60 %",
        ),
        stress(
            "hot:co2_rel", "co2_c_kg_ha_rel", hot, warn=(1.15, 1.6), fail=(0.9, INF)
        ),
        stress(
            "hot:volatilisation_rel", "volatilization_kg_ha_rel", hot, warn=(1.0, INF)
        ),
        stress("hot:deep_perc_rel", "deep_perc_mm_rel", hot, warn=(0, 1.0)),
        stress("hot:no3_leached_rel", "no3_leached_kg_ha_rel", hot, warn=(0, 1.05)),
    ]


def _limitation_checks() -> list[Check]:
    """Bands on what limits growth and on the topsoil redox state.

    Every run is rain-fed on a drained profile, so the topsoil must stay
    aerobic and iron must never reach the toxic range that only flooded rice
    paddies show. Presets that start below a critical micronutrient level,
    or a sulfate pool that binds growth for most of the season, point at the
    soil data rather than the weather.
    """
    cat = "limitation"
    return [
        Check(
            "topsoil_anoxic_days",
            "topsoil_anoxic_days",
            warn=(-INF, 3),
            fail=(-INF, 15),
            applies=NORMAL,
            category=cat,
            source="drained topsoil at field capacity keeps >10 % air-filled porosity "
            "and stays aerobic (Grable & Siemer 1968)",
        ),
        Check(
            "topsoil_co2_median",
            "co2_0_median_frac",
            warn=(0.001, 0.05),
            fail=(-INF, 0.10),
            applies=NORMAL,
            category=cat,
            source="season-median soil-air CO2 in cropped topsoil runs 0.1-5 %; "
            "medians above 10 % occur only in flooded or compacted profiles "
            "(Glinski & Stepniewski 1985). The season maximum is reported as "
            "co2_0_max_frac but not graded: single wet days and the "
            "post-initialisation SOM flush dominate it",
        ),
        Check(
            "anaerobic_layer_days",
            "anaerobic_layer_days",
            warn=(-INF, 30),
            applies=_and(NORMAL, _not(PEAT)),
            category=cat,
            source="a drained mineral profile has anaerobic layers only after heavy "
            "rain, not for weeks",
        ),
        Check(
            "fe_toxic_days",
            "fe_toxic_days",
            warn=(-INF, 0),
            fail=(-INF, 10),
            applies=NORMAL,
            category=cat,
            source="Fe toxicity (>300 ppm available Fe) is a flooded-rice disorder "
            "(Becker & Asch 2005), never seen on drained soils",
        ),
        Check(
            "fe_deficient_days",
            "fe_deficient_days",
            warn=(-INF, 30),
            applies=_and(NORMAL, _not(CALCAREOUS)),
            category=cat,
            source="available Fe below the 4.5 ppm DTPA critical level all season "
            "means a non-calcareous preset starts deficient by accident "
            "(Lindsay & Norvell 1978)",
        ),
        Check(
            "fe_deficient_days:calcareous",
            "fe_deficient_days",
            applies=_and(NORMAL, CALCAREOUS),
            category=cat,
            info=True,
            source="Fe deficiency is allowed on the calcareous sand: Fe(III) oxides "
            "are insoluble at its pH, so DTPA-Fe sits below the critical level and "
            "lime-induced chlorosis is the intended limitation (Lindsay 1979)",
        ),
        Check(
            "zn_deficient_days",
            "zn_deficient_days",
            warn=(-INF, 30),
            applies=_and(NORMAL, NOT_LOW_SOM),
            category=cat,
            source="available Zn below the 0.8 ppm DTPA critical level all season "
            "means the preset starts deficient by accident (Lindsay & Norvell 1978)",
        ),
        Check(
            "zn_deficient_days:low_som",
            "zn_deficient_days",
            applies=_and(NORMAL, LOW_SOM),
            category=cat,
            info=True,
            source="Zn deficiency is allowed on low-SOM sands: DTPA-Zn 0.3-0.8 mg/kg "
            "is typical of Sahelian, Sudanian and arid sands, where Zn is the most "
            "widespread micronutrient deficiency (Sillanpaa 1982; Alloway 2008)",
        ),
        Check(
            "s_binding_days",
            "binding_days_s",
            warn=(-INF, 30),
            fail=(-INF, 90),
            applies=_and(NORMAL, VIABLE),
            category=cat,
            source="sulfur deficiency in unfertilised crops is episodic, "
            "not the season-long limiting factor (Scherer 2001)",
        ),
        Check(
            "growth_factor_mean_humid",
            "growth_factor_mean",
            warn=(0.6, INF),
            fail=(0.3, INF),
            applies=_and(NORMAL, VIABLE, _clim(NL, KENYA)),
            category=cat,
            source="a rain-fed crop in a humid climate on an unfertilised but healthy "
            "soil keeps its season-mean growth factor above ~0.6",
        ),
    ]


def _anchor(
    crop: str,
    climate: str,
    metric: str,
    value: float,
    pct: float = 1.0,
    *,
    abs_tol: float | None = None,
    info: bool = False,
) -> Check:
    if abs_tol is not None:
        lo, hi = value - abs_tol, value + abs_tol
    else:
        lo, hi = sorted((value * (1 - pct / 100.0), value * (1 + pct / 100.0)))
    return Check(
        f"anchor:{crop}:{CLIMATE_SHORT[climate]}:{metric}",
        metric,
        warn=(lo, hi),
        applies=_and(ANCHOR_ROW, _crop(crop), _clim(climate)),
        category="anchor",
        source=f"realism suite value {value}",
        info=info,
    )


def _anchor_exact(crop: str, climate: str, metric: str, value: Any) -> Check:
    return Check(
        f"anchor:{crop}:{CLIMATE_SHORT[climate]}:{metric}",
        metric,
        applies=_and(ANCHOR_ROW, _crop(crop), _clim(climate)),
        category="anchor",
        source=f"realism suite value {value}",
        expect=value,
        expect_severity="WARN",
    )


def _anchor_checks() -> list[Check]:
    return [
        _anchor("maize", NL, "agb_g_m2", 1363, 3),
        _anchor_exact("maize", NL, "final_stage", "GRAIN_FILL"),
        _anchor("maize", NL, "et_actual_mm", 392, 3),
        _anchor("maize", KENYA, "agb_g_m2", 1860.0),
        _anchor("maize", KENYA, "grain_g_m2", 597.5, 3),
        _anchor("maize", KENYA, "harvest_index", 0.318, 3),
        _anchor_exact("maize", KENYA, "final_stage", "MATURITY"),
        _anchor_exact("maize", KENYA, "day_flowering", 78),
        _anchor_exact("maize", KENYA, "day_maturity", 173),
        _anchor("maize", KENYA, "rain_mm", 913.5),
        _anchor("maize", KENYA, "evap_mm", 171.7),
        _anchor("maize", KENYA, "transp_mm", 395.7),
        _anchor("maize", KENYA, "runoff_mm", 134.8),
        _anchor("maize", KENYA, "deep_perc_mm", 329.8),
        _anchor("maize", KENYA, "no3_leached_kg_ha", 39.1),
        _anchor("maize", KENYA, "denitrification_kg_ha", 0.0, abs_tol=0.5),
        _anchor("maize", KENYA, "volatilization_kg_ha", 0.18, abs_tol=0.05),
        _anchor("maize", KENYA, "som_min_n_kg_ha", 149.2),
        _anchor("maize", KENYA, "n_uptake_kg_ha", 139.2),
        _anchor("maize", KENYA, "n_massflow_supply_kg_ha", 1.95, abs_tol=0.1),
        _anchor("maize", KENYA, "som_c_change_pct", -2.0, 3),
        _anchor_exact("maize", KENYA, "drought_senescence_events", 22.0),
        _anchor("maize", KENYA, "so4_leached_kg_ha", 16.0),
        _anchor("maize", KENYA, "s_avail_end_kg_ha", 45.0),
        _anchor_exact("maize", KENYA, "binding_days_s", 0),
        _anchor("maize", SAHEL, "agb_g_m2", 778, 3),
        _anchor("maize", SAHEL, "grain_g_m2", 177, 3),
        _anchor("maize", SAHEL, "harvest_index", 0.227, 3),
        _anchor_exact("maize", SAHEL, "final_stage", "MATURITY"),
        _anchor("maize", SAHEL, "no3_leached_kg_ha", 0.3, abs_tol=0.7),
        _anchor("sorghum", SAHEL, "agb_g_m2", 920, 3),
        _anchor("sorghum", NL, "agb_g_m2", 941, 3),
        _anchor("spring_wheat", NL, "agb_g_m2", 450, 3),
        _anchor_exact("spring_wheat", NL, "final_stage", "MATURITY"),
        _anchor("spring_wheat", KENYA, "agb_g_m2", 1459, 3),
        _anchor("winter_wheat", NL, "agb_g_m2", 375, 3),
        _anchor("winter_wheat", NL, "grain_g_m2", 206, 3),
        _anchor("winter_wheat", NL, "harvest_index", 0.55, abs_tol=0.005),
        _anchor_exact("winter_wheat", NL, "final_stage", "MATURITY"),
        _anchor("winter_wheat", NL, "mineral_n_peak_kg_ha", 98.1, 3),
        _anchor("winter_wheat", NL, "som_c_change_pct", -2.16, 3),
        _anchor("winter_wheat", SAHEL, "agb_g_m2", 202, 3),
        _anchor_exact("winter_wheat", SAHEL, "final_stage", "VEGETATIVE"),
        _anchor_exact("winter_wheat", KENYA, "final_stage", "VEGETATIVE"),
        _anchor("rice", KENYA, "agb_g_m2", 1020, 3),
        _anchor_exact("rice", KENYA, "final_stage", "MATURITY"),
        _anchor("rice", SAHEL, "agb_g_m2", 231, 3),
        _anchor("grape", SAHEL, "agb_g_m2", 8, abs_tol=3),
        _anchor("grape", NL, "agb_g_m2", 132, 3),
    ]


def build_checks() -> list[Check]:
    checks: list[Check] = list(INVARIANTS)
    for band in CROP_BANDS:
        checks.extend(_expand_crop_band(band))
    checks.extend(PLANT_CHECKS)
    checks.extend(_water_checks())
    checks.extend(_nitrogen_checks())
    checks.extend(_som_checks())
    checks.extend(_limitation_checks())
    checks.extend(_stress_checks())
    checks.extend(_anchor_checks())
    names = [c.name for c in checks]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"duplicate check names: {duplicates}")
    return checks


# ---------------------------------------------------------------------------
# Relative metrics, soil-ordering checks and climate/crop contrasts
# ---------------------------------------------------------------------------


def _finite(value: Any) -> bool:
    return (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def attach_relative_metrics(results: list[RunResult]) -> None:
    """Express each stress run relative to its normal-weather twin.

    The twin shares crop, soil, climate and seed. Ratios are left NaN when the
    normal value sits below the metric's floor, so a ratio never amplifies
    noise around zero.
    """
    normals = {
        (r.spec.crop, r.spec.soil, r.spec.climate, r.spec.seed): r.scalars
        for r in results
        if r.status == "ok" and r.spec.scenario == "normal"
    }
    for result in results:
        if result.status != "ok" or result.spec.scenario == "normal":
            continue
        spec = result.spec
        ref = normals.get((spec.crop, spec.soil, spec.climate, spec.seed))
        if ref is None:
            continue
        s = result.scalars
        for metric, floor in REL_METRICS:
            if metric == "day_maturity":
                continue
            value, base = s.get(metric), ref.get(metric)
            if _finite(value) and _finite(base) and base >= floor and base > 0:
                s[f"{metric}_rel"] = value / base
        s["ref_agb_g_m2"] = ref["agb_g_m2"]
        s["ref_grain_g_m2"] = ref["grain_g_m2"]
        s["ref_day_maturity"] = ref["day_maturity"]
        both_reached = s["reached_maturity"] == 1 and ref["reached_maturity"] == 1
        if both_reached and ref["day_maturity"] > 0:
            s["day_maturity_rel"] = s["day_maturity"] / ref["day_maturity"]
            s["day_maturity_delta"] = s["day_maturity"] - ref["day_maturity"]
        s["hot_maturity_lost"] = (
            1.0 if ref["reached_maturity"] == 1 and s["reached_maturity"] != 1 else 0.0
        )
        if ref["grain_g_m2"] >= 20:
            if _finite(s.get("grain_g_m2_rel")) and _finite(s.get("agb_g_m2_rel")):
                s["grain_minus_agb_rel"] = s["grain_g_m2_rel"] - s["agb_g_m2_rel"]
            if _finite(s.get("harvest_index")) and _finite(ref.get("harvest_index")):
                s["harvest_index_delta"] = s["harvest_index"] - ref["harvest_index"]


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = rank
        i = j + 1
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman rank correlation.

    NaN for fewer than three points or a constant series.
    """
    if len(x) < 3 or len(x) != len(y):
        return math.nan
    rx, ry = _ranks(x), _ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    if sxx <= 0 or syy <= 0:
        return math.nan
    return sxy / math.sqrt(sxx * syy)


def _ok_scalars(results: list[RunResult]) -> list[dict[str, Any]]:
    return [r.scalars for r in results if r.status == "ok"]


GroupKey = tuple[str, str, str, int]


def _group_rows(rows: list[dict[str, Any]]) -> dict[GroupKey, list[dict[str, Any]]]:
    groups: dict[GroupKey, list[dict[str, Any]]] = {}
    for s in rows:
        key = (s["crop"], s["climate"], s["scenario"], s["seed"])
        groups.setdefault(key, []).append(s)
    return groups


def _group_finding(
    group_id: str,
    scope: str,
    name: str,
    metric: str,
    value: Any,
    band: str,
    severity: str,
    *,
    source: str = "",
    detail: str = "",
    known: str = "",
) -> Finding:
    category = "ordering" if scope == "group" else "contrast"
    return Finding(
        run_id=group_id,
        scope=scope,
        check=name,
        category=category,
        metric=metric,
        value=value,
        band=band,
        severity=severity,
        source=source,
        known=known,
        detail=detail,
        distance=1.0,
    )


def _values_by_soil(rows: list[dict[str, Any]], metric: str) -> str:
    ordered = sorted(rows, key=lambda s: s["soil"])
    return ", ".join(f"{s['soil']}={_fmt_num(s.get(metric))}" for s in ordered)


def _corr_check(
    rows: list[dict[str, Any]],
    group_id: str,
    name: str,
    metric: str,
    order_by: str,
    warn_rho: float,
    fail_rho: float | None,
    *,
    source: str = "",
    min_max: float = 0.0,
) -> Finding | None:
    usable = [s for s in rows if _finite(s.get(metric)) and _finite(s.get(order_by))]
    if len(usable) < 3:
        return None
    if max(abs(s[metric]) for s in usable) < min_max:
        return None
    rho = spearman([s[order_by] for s in usable], [s[metric] for s in usable])
    if math.isnan(rho):
        return None
    band = f"spearman(rho) >= {warn_rho}" + (f", fail < {fail_rho}" if fail_rho else "")
    severity = None
    if fail_rho is not None and rho < fail_rho:
        severity = "FAIL"
    elif rho < warn_rho:
        severity = "WARN"
    if severity is None:
        return None
    ordered = sorted(usable, key=lambda s: s[order_by])
    detail = " < ".join(f"{s['soil']}:{_fmt_num(s[metric])}" for s in ordered)
    return _group_finding(
        group_id,
        "group",
        name,
        f"rho({metric} ~ {order_by})",
        round(rho, 3),
        band,
        severity,
        source=source,
        detail=f"by {order_by}: {detail}",
    )


def _desc_violations(
    labelled: Sequence[tuple[str, float]], tolerance: float, floor: float
) -> list[str]:
    """Report neighbours in a supposedly descending series that invert by more than
    ``tolerance`` (relative) while the larger value exceeds ``floor``."""
    out = []
    for (name_a, a), (name_b, b) in pairwise(labelled):
        if b > a * (1 + tolerance) and b > floor:
            out.append(f"{name_b}={_fmt_num(b)} > {name_a}={_fmt_num(a)}")
    return out


def _trio(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]] | None:
    by_soil = {s["soil"]: s for s in rows}
    if all(soil in by_soil for soil in TEMPERATE_TRIO):
        return {soil: by_soil[soil] for soil in TEMPERATE_TRIO}
    return None


def _trio_series(
    trio: dict[str, dict[str, Any]], metric: str
) -> list[tuple[str, float]]:
    return [(soil, float(trio[soil][metric])) for soil in TEMPERATE_TRIO]


STAGE_DAY_KEYS = (
    "day_emerged",
    "day_vegetative",
    "day_flowering",
    "day_grain_fill",
    "day_maturity",
)


def _soil_group_checks(key: GroupKey, rows: list[dict[str, Any]]) -> list[Finding]:
    crop, climate, scenario, seed = key
    gid = f"{crop}|{climate}|{scenario}|s{seed}"
    rep = rows[0]
    viable = rep["fit"] != "not_grown"
    productive = viable and any(
        _finite(s["agb_g_m2"]) and s["agb_g_m2"] >= 300 for s in rows
    )
    mineral = [s for s in rows if s["soil_class"] != "PEAT"]
    water_limited = scenario == "drought" or (scenario == "normal" and climate == SAHEL)
    findings: list[Finding] = []

    def add(finding: Finding | None) -> None:
        if finding is not None:
            findings.append(finding)

    if productive and water_limited:
        add(
            _corr_check(
                mineral,
                gid,
                "S1:agb_increases_with_pawc",
                "agb_g_m2",
                "pawc_mm",
                0.5,
                None,
                source="water-limited biomass follows plant-available water capacity",
            )
        )
        if climate == SAHEL and scenario == "normal":
            add(
                _corr_check(
                    mineral,
                    gid,
                    "S6:et_increases_with_pawc",
                    "et_actual_mm",
                    "pawc_mm",
                    0.5,
                    None,
                )
            )
    trio = _trio(rows)
    if trio is not None:
        sand, clay = trio["sandy_temperate"], trio["clay_temperate"]
        if (
            productive
            and water_limited
            and sand["water_stress_days"] < clay["water_stress_days"] - 3
        ):
            add(
                _group_finding(
                    gid,
                    "group",
                    "S2:water_stress_days_fall_with_pawc",
                    "water_stress_days",
                    f"sand {sand['water_stress_days']} vs clay "
                    f"{clay['water_stress_days']}",
                    "sand >= clay - 3 d",
                    "WARN",
                )
            )
        bad = _desc_violations(_trio_series(trio, "deep_perc_mm"), 0.10, 20.0)
        if bad:
            add(
                _group_finding(
                    gid,
                    "group",
                    "S3:deep_perc_sand_ge_loam_ge_clay",
                    "deep_perc_mm",
                    "; ".join(bad),
                    "sand >= loam >= clay (10 %)",
                    "FAIL",
                    detail=_values_by_soil(list(trio.values()), "deep_perc_mm"),
                )
            )
        leach = _trio_series(trio, "no3_leached_kg_ha")
        if max(v for _, v in leach) >= 5.0:
            bad = _desc_violations(leach, 0.15, 0.0)
            if bad:
                add(
                    _group_finding(
                        gid,
                        "group",
                        "S4:no3_leached_sand_ge_loam_ge_clay",
                        "no3_leached_kg_ha",
                        "; ".join(bad),
                        "sand >= loam >= clay (15 %)",
                        "WARN",
                    )
                )
        denit = _trio_series(trio, "denitrification_kg_ha")
        if denit[2][1] >= 1.0:
            bad = _desc_violations(list(reversed(denit)), 0.10, 0.0)
            if bad:
                severity = "FAIL" if denit[0][1] > denit[2][1] else "WARN"
                add(
                    _group_finding(
                        gid,
                        "group",
                        "S8:denitrification_clay_ge_loam_ge_sand",
                        "denitrification_kg_ha",
                        "; ".join(bad),
                        "clay >= loam >= sand",
                        severity,
                        source="denitrification needs the anaerobic microsites of "
                        "wet, fine soils",
                    )
                )
    with_cn = [
        s
        for s in rows
        if _finite(s.get("curve_number")) and _finite(s.get("runoff_mm"))
    ]
    inversions = [
        f"{b['soil']}(CN {b['curve_number']:.0f})={_fmt_num(b['runoff_mm'])} < "
        f"{a['soil']}(CN {a['curve_number']:.0f})={_fmt_num(a['runoff_mm'])}"
        for a in with_cn
        for b in with_cn
        if a["curve_number"] < b["curve_number"]
        and b["runoff_mm"] < a["runoff_mm"] - 0.1
    ]
    if inversions:
        add(
            _group_finding(
                gid,
                "group",
                "S5:runoff_rises_with_curve_number",
                "runoff_mm",
                "; ".join(inversions[:4]),
                "non-decreasing in CN",
                "FAIL",
                source="SCS curve number: higher CN, more runoff from the same rain",
            )
        )
    if scenario != "normal":
        return findings
    if productive and climate in (NL, KENYA):
        ets = [
            s["et_actual_mm"]
            for s in mineral
            if _finite(s.get("et_actual_mm")) and s["et_actual_mm"] > 0
        ]
        if len(ets) >= 2 and max(ets) / min(ets) > 1.25:
            add(
                _group_finding(
                    gid,
                    "group",
                    "S6:et_spread_across_soils_humid",
                    "et_actual_mm max/min",
                    round(max(ets) / min(ets), 3),
                    "<= 1.25",
                    "WARN",
                    source="in humid climates soil texture changes seasonal ET only "
                    "modestly",
                    detail=_values_by_soil(mineral, "et_actual_mm"),
                )
            )
    for metric in ("som_min_n_kg_ha", "mineral_n_peak_kg_ha"):
        add(
            _corr_check(
                rows,
                gid,
                f"S7:{metric}_tracks_som_c",
                metric,
                "som_c_start_kg_ha",
                0.8,
                0.5,
                source="N supply scales with the soil organic matter stock",
            )
        )
    peat = [s for s in rows if s["soil_class"] == "PEAT"]
    if peat and mineral:
        p = peat[0]
        top_mineral = max(mineral, key=lambda s: s["som_min_n_kg_ha"])
        if p["som_min_n_kg_ha"] <= top_mineral["som_min_n_kg_ha"]:
            add(
                _group_finding(
                    gid,
                    "group",
                    "S9:peat_mineralises_most",
                    "som_min_n_kg_ha",
                    f"peat {_fmt_num(p['som_min_n_kg_ha'])} <= "
                    f"{top_mineral['soil']} {_fmt_num(top_mineral['som_min_n_kg_ha'])}",
                    "peat > every mineral soil",
                    "WARN",
                )
            )
        loam = next((s for s in rows if s["soil"] == "loam_temperate"), None)
        if (
            productive
            and climate in (NL, KENYA)
            and loam
            and p["agb_g_m2"] < 0.9 * loam["agb_g_m2"]
        ):
            add(
                _group_finding(
                    gid,
                    "group",
                    "S9:peat_agb_not_below_loam",
                    "agb_g_m2",
                    f"peat {_fmt_num(p['agb_g_m2'])} vs loam "
                    f"{_fmt_num(loam['agb_g_m2'])}",
                    "peat >= 0.9 x loam",
                    "WARN",
                    source="a well-drained peat is not N-limited and grows at least "
                    "as much as a loam",
                )
            )
    for stage_key in STAGE_DAY_KEYS:
        days = {s[stage_key] for s in rows}
        if len(days) > 1:
            add(
                _group_finding(
                    gid,
                    "group",
                    "S10:stage_days_identical_across_soils",
                    stage_key,
                    _values_by_soil(rows, stage_key),
                    "one value",
                    "FAIL",
                    source="phenology is thermal-time driven and independent of the "
                    "soil",
                )
            )
    if productive:
        add(
            _corr_check(
                [s for s in rows if s["agb_g_m2"] >= 300],
                gid,
                "S12:nni_tracks_som_c",
                "nni_final",
                "som_c_start_kg_ha",
                0.5,
                None,
                source="crops on richer soils end the season better supplied with N",
            )
        )
        loam = next((s for s in rows if s["soil"] == "loam_temperate"), None)
        for s in rows:
            if loam is None or s["som_c_start_kg_ha"] >= LOW_SOM_C_KG_HA or s is loam:
                continue
            if s["mineral_n_peak_kg_ha"] >= loam["mineral_n_peak_kg_ha"]:
                add(
                    _group_finding(
                        gid,
                        "group",
                        "S13:low_som_soil_peaks_below_loam",
                        "mineral_n_peak_kg_ha",
                        f"{s['soil']} {_fmt_num(s['mineral_n_peak_kg_ha'])} >= "
                        f"loam {_fmt_num(loam['mineral_n_peak_kg_ha'])}",
                        "low-SOM < loam_temperate",
                        "WARN",
                    )
                )
            if loam["agb_g_m2"] >= 300 and s["plant_n_kg_ha"] >= loam["plant_n_kg_ha"]:
                add(
                    _group_finding(
                        gid,
                        "group",
                        "S13:low_som_soil_plant_n_below_loam",
                        "plant_n_kg_ha",
                        f"{s['soil']} {_fmt_num(s['plant_n_kg_ha'])} >= "
                        f"loam {_fmt_num(loam['plant_n_kg_ha'])}",
                        "low-SOM < loam_temperate",
                        "WARN",
                    )
                )
    return findings


def evaluate_groups(results: list[RunResult]) -> list[Finding]:
    findings: list[Finding] = []
    for key, rows in sorted(_group_rows(_ok_scalars(results)).items()):
        findings.extend(_soil_group_checks(key, rows))
    return findings


RowIndex = dict[tuple[str, str, str, str, int], dict[str, Any]]


def _climate_contrasts(idx: RowIndex, crop: str, soil: str, seed: int) -> list[Finding]:
    rows = {c: idx.get((crop, soil, c, "normal", seed)) for c in ALL_CLIMATES}
    nl, ke, sa = rows[NL], rows[KENYA], rows[SAHEL]
    cid = f"{crop}|{soil}|normal|s{seed}"
    out: list[Finding] = []

    def contrast(
        name: str, metric: str, value: Any, band: str, severity: str, **kw: Any
    ) -> None:
        out.append(
            _group_finding(cid, "contrast", name, metric, value, band, severity, **kw)
        )

    if nl and ke and sa:
        et0 = (sa["et0_mean_mm_d"], ke["et0_mean_mm_d"], nl["et0_mean_mm_d"])
        if not et0[0] > et0[1] > et0[2]:
            contrast(
                "C1:et0_sahel_gt_kenya_gt_nl",
                "et0_mean_mm_d",
                f"sahel {_fmt_num(et0[0])}, kenya {_fmt_num(et0[1])}, nl "
                f"{_fmt_num(et0[2])}",
                "Sahel > Kenya > NL",
                "WARN",
            )
        leach = (
            ke["no3_leached_kg_ha"],
            nl["no3_leached_kg_ha"],
            sa["no3_leached_kg_ha"],
        )
        if max(leach) >= 5.0 and not leach[0] > leach[1] > leach[2]:
            contrast(
                "C5:no3_leached_kenya_gt_nl_gt_sahel",
                "no3_leached_kg_ha",
                f"kenya {_fmt_num(leach[0])}, nl {_fmt_num(leach[1])}, sahel "
                f"{_fmt_num(leach[2])}",
                "Kenya > NL > Sahel",
                "WARN",
                source="leaching follows drainage: wettest climate leaches most",
            )
    reached = [
        (c, r)
        for c, r in ((SAHEL, sa), (KENYA, ke), (NL, nl))
        if r and r["reached_maturity"] == 1
    ]
    for (ca, a), (cb, b) in pairwise(reached):
        if a["day_maturity"] >= b["day_maturity"]:
            contrast(
                "C2:maturity_earlier_in_warmer_climate",
                "day_maturity",
                f"{CLIMATE_SHORT[ca]} {a['day_maturity']} >= {CLIMATE_SHORT[cb]} "
                f"{b['day_maturity']}",
                "Sahel < Kenya < NL",
                "WARN",
            )
    if nl and ke:
        if ke["som_min_n_kg_ha"] <= nl["som_min_n_kg_ha"]:
            contrast(
                "C7:som_min_n_kenya_gt_nl",
                "som_min_n_kg_ha",
                f"kenya {_fmt_num(ke['som_min_n_kg_ha'])} <= nl "
                f"{_fmt_num(nl['som_min_n_kg_ha'])}",
                "Kenya > NL",
                "WARN",
                source="warmer, wetter soil decomposes faster",
            )
    if crop == "maize":
        if ke and sa and ke["agb_g_m2"] < sa["agb_g_m2"]:
            contrast(
                "C3:maize_kenya_ge_sahel",
                "agb_g_m2",
                f"kenya {_fmt_num(ke['agb_g_m2'])} < sahel {_fmt_num(sa['agb_g_m2'])}",
                "Kenya >= Sahel",
                "WARN",
            )
        agbs = [
            r["agb_g_m2"]
            for r in (nl, ke, sa)
            if r and r["fit"] != "not_grown" and r["agb_g_m2"] > 0
        ]
        if len(agbs) >= 2 and max(agbs) / min(agbs) >= 2.0:
            contrast(
                "C3:maize_cross_climate_spread",
                "agb_g_m2 max/min",
                round(max(agbs) / min(agbs), 2),
                "< 2.0",
                "WARN",
                source="rain-fed maize biomass differs less than twofold across these "
                "climates",
            )
        if nl and ke and nl["agb_g_m2"] > ke["agb_g_m2"]:
            contrast(
                "C3:maize_nl_gt_kenya",
                "agb_g_m2",
                f"nl {_fmt_num(nl['agb_g_m2'])} > kenya {_fmt_num(ke['agb_g_m2'])}",
                "info",
                "INFO",
                known=KNOWN_NL_GT_KENYA,
            )
    if ke and sa and ke["fit"] != "not_grown" and sa["fit"] != "not_grown":
        if not sa["et_over_et0"] < ke["et_over_et0"]:
            contrast(
                "C4:et_over_et0_sahel_lt_kenya",
                "et_over_et0",
                f"sahel {_fmt_num(sa['et_over_et0'])} vs kenya "
                f"{_fmt_num(ke['et_over_et0'])}",
                "Sahel < Kenya",
                "WARN",
            )
    return out


def _crop_contrasts(idx: RowIndex, soil: str, seed: int) -> list[Finding]:
    out: list[Finding] = []

    def row(crop: str, climate: str) -> dict[str, Any] | None:
        return idx.get((crop, soil, climate, "normal", seed))

    def contrast(
        climate: str,
        name: str,
        metric: str,
        value: Any,
        band: str,
        severity: str,
        **kw: Any,
    ) -> None:
        cid = f"*|{soil}|{climate}|normal|s{seed}"
        out.append(
            _group_finding(cid, "contrast", name, metric, value, band, severity, **kw)
        )

    sorghum = row("sorghum", SAHEL)
    if sorghum:
        for other in ("maize", "winter_wheat", "grape"):
            o = row(other, SAHEL)
            if o and o["agb_g_m2"] >= sorghum["agb_g_m2"]:
                severity = (
                    "FAIL"
                    if other == "maize"
                    and soil == "loam_temperate"
                    and o["agb_g_m2"] > 1.05 * sorghum["agb_g_m2"]
                    else "WARN"
                )
                contrast(
                    SAHEL,
                    f"K1:sahel_sorghum_outyields_{other}",
                    "agb_g_m2",
                    f"sorghum {_fmt_num(sorghum['agb_g_m2'])} <= {other} "
                    f"{_fmt_num(o['agb_g_m2'])}",
                    f"sorghum > {other}",
                    severity,
                    source="sorghum is the drought-adapted Sahel cereal",
                )
    maize_ke, wheat_ke = row("maize", KENYA), row("spring_wheat", KENYA)
    if maize_ke and wheat_ke and maize_ke["agb_g_m2"] < wheat_ke["agb_g_m2"]:
        contrast(
            KENYA,
            "K2:kenya_maize_ge_spring_wheat",
            "agb_g_m2",
            f"maize {_fmt_num(maize_ke['agb_g_m2'])} < wheat "
            f"{_fmt_num(wheat_ke['agb_g_m2'])}",
            "maize >= wheat",
            "WARN",
            source="C4 maize outproduces C3 wheat in the warm highlands",
        )
    ww_nl, sw_nl = row("winter_wheat", NL), row("spring_wheat", NL)
    if ww_nl and sw_nl and ww_nl["agb_g_m2"] < sw_nl["agb_g_m2"] / 1.2:
        contrast(
            NL,
            "K3:nl_winter_wheat_not_far_below_spring_wheat",
            "agb_g_m2",
            f"winter {_fmt_num(ww_nl['agb_g_m2'])} vs spring "
            f"{_fmt_num(sw_nl['agb_g_m2'])}",
            "winter >= spring / 1.2",
            "WARN",
            source="autumn-sown wheat outyields spring wheat in NL practice",
            known=KNOWN_LOW_WHEAT,
        )
    for climate in (NL, KENYA):
        grape = row("grape", climate)
        if not grape:
            continue
        for cereal in CEREALS:
            c = row(cereal, climate)
            if c and c["fit"] != "not_grown" and grape["agb_g_m2"] >= c["agb_g_m2"]:
                contrast(
                    climate,
                    f"K5:grape_below_{cereal}",
                    "agb_g_m2",
                    f"grape {_fmt_num(grape['agb_g_m2'])} >= {cereal} "
                    f"{_fmt_num(c['agb_g_m2'])}",
                    f"grape < {cereal}",
                    "WARN",
                    source="a vine canopy accumulates far less seasonal dry matter "
                    "than a cereal",
                )
    return out


def evaluate_contrasts(results: list[RunResult]) -> list[Finding]:
    idx: RowIndex = {
        (s["crop"], s["soil"], s["climate"], s["scenario"], s["seed"]): s
        for s in _ok_scalars(results)
    }
    seeds = sorted({k[4] for k in idx})
    soils = sorted({k[1] for k in idx})
    crops = sorted({k[0] for k in idx})
    findings: list[Finding] = []
    for seed, soil in product(seeds, soils):
        for crop in crops:
            findings.extend(_climate_contrasts(idx, crop, soil, seed))
        findings.extend(_crop_contrasts(idx, soil, seed))
    return findings


# ---------------------------------------------------------------------------
# Evaluation and grading
# ---------------------------------------------------------------------------

GRADE_ORDER = ("ERROR", "FAIL", "WARN", "PASS", "EXPECTED")
GRADE_CODE = {"ERROR": "E", "FAIL": "F", "WARN": "W", "PASS": "P", "EXPECTED": "X"}


def evaluate_run(result: RunResult, checks: list[Check]) -> list[Finding]:
    if result.status != "ok":
        return [
            Finding(
                run_id=result.spec.run_id,
                scope="run",
                check="run_completed",
                category="invariant",
                metric="status",
                value=result.error,
                band="== ok",
                severity="ERROR",
                detail=result.traceback_tail,
                distance=1.0,
            )
        ]
    findings = []
    for check in checks:
        finding = evaluate_check(check, result.scalars)
        if finding is not None:
            findings.append(finding)
    return findings


def grade_run(result: RunResult) -> str:
    if result.status != "ok":
        return "ERROR"
    severities = {f.severity for f in result.findings if f.scope == "run"}
    if "FAIL" in severities:
        return "FAIL"
    if "WARN" in severities:
        return "WARN"
    if result.spec.fit == "not_grown":
        return "EXPECTED"
    return "PASS"


def evaluate_all(results: list[RunResult], checks: list[Check]) -> list[Finding]:
    """Grade every run in place; return the group-level findings.

    Group-level findings are the soil-ordering, climate and crop contrasts.
    """
    attach_relative_metrics(results)
    for result in results:
        result.findings = evaluate_run(result, checks)
        result.grade = grade_run(result)
    return evaluate_groups(results) + evaluate_contrasts(results)


# ---------------------------------------------------------------------------
# Output: CSV tables, daily traces, report, plots
# ---------------------------------------------------------------------------


def _ordered_keys(rows: Sequence[dict[str, Any]]) -> list[str]:
    keys: dict[str, None] = {}
    for row in rows:
        for key in row:
            keys.setdefault(key, None)
    return list(keys)


def _csv_value(value: Any) -> Any:
    if isinstance(value, float):
        return "" if math.isnan(value) else f"{value:.6g}"
    return value


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    keys = _ordered_keys(rows)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_value(row.get(k, "")) for k in keys})


def _git_info() -> tuple[str, bool]:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False
    return sha or "unknown", bool(status)


def _cell(value: Any) -> str:
    if isinstance(value, float):
        return "n/a" if math.isnan(value) else _fmt_num(value)
    return str(value).replace("|", "\\|").replace("\n", " ")


def _md_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        lines.append("| " + " | ".join(_cell(v) for v in row) + " |")
    lines.append("")
    return lines


def _section_errors(results: list[RunResult]) -> list[str]:
    errors = [r for r in results if r.status != "ok"]
    if not errors:
        return []
    lines = ["## Runs that raised", ""]
    for r in errors:
        lines += [
            f"### {r.spec.run_id}",
            "",
            f"`{r.error}`",
            "",
            "```",
            r.traceback_tail.rstrip(),
            "```",
            "",
        ]
    return lines


def _by_check(findings: Sequence[Finding]) -> dict[str, list[Finding]]:
    groups: dict[str, list[Finding]] = {}
    for f in findings:
        groups.setdefault(f.check, []).append(f)
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def _value_range(findings: Sequence[Finding]) -> str:
    numeric = [float(f.value) for f in findings if _finite(f.value)]
    if not numeric:
        return _cell(findings[0].value)
    if len(numeric) == 1:
        return _fmt_num(numeric[0])
    return f"{_fmt_num(min(numeric))} .. {_fmt_num(max(numeric))}"


def _section_by_check(title: str, findings: Sequence[Finding], worst: int) -> list[str]:
    lines = [f"## {title}", ""]
    if not findings:
        return [*lines, "None.", ""]
    groups = _by_check(findings)
    lines.append(f"{len(findings)} findings across {len(groups)} checks.")
    lines.append("")
    summary = [
        (
            name,
            len(group),
            group[0].metric,
            group[0].band,
            _value_range(group),
            "known" if group[0].known else "new",
        )
        for name, group in groups.items()
    ]
    lines += _md_table(["check", "runs", "metric", "band", "values", "status"], summary)
    if worst <= 0:
        return lines
    for name, group in groups.items():
        lines.append(f"### {name}")
        lines.append("")
        head = group[0]
        if head.source:
            lines.append(f"Expectation: {head.source}.")
        if head.known:
            lines.append(f"Known limitation: {head.known}.")
        lines.append("")
        top = sorted(group, key=lambda f: -f.distance)[:worst]
        lines += _md_table(
            ["run", "value", "band", "note"],
            [(f.run_id, f.value, f.band, f.detail) for f in top],
        )
    return lines


def _section_allowed(findings: Sequence[Finding]) -> list[str]:
    """Informational checks whose out-of-band value is the intended behaviour.

    A check marked ``info`` never grades its run. When it also carries a
    ``source``, that source states why the value is allowed (a preset that is
    deficient on purpose, for example), and the affected runs are listed here
    so that the allowance stays visible instead of disappearing from the
    report. Anchors are informational too but have their own section.
    """
    lines = ["## Allowed by design", ""]
    rows = [
        f
        for f in findings
        if f.severity == "INFO" and f.category != "anchor" and f.source
    ]
    if not rows:
        return [*lines, "None.", ""]
    groups = _by_check(rows)
    lines.append(
        f"{len(rows)} informational findings across {len(groups)} checks; "
        "none affects a run grade."
    )
    lines.append("")
    lines += _md_table(
        ["check", "runs", "metric", "values", "why allowed"],
        [
            (name, len(group), group[0].metric, _value_range(group), group[0].source)
            for name, group in groups.items()
        ],
    )
    return lines


def _section_groups(group_findings: Sequence[Finding]) -> list[str]:
    lines = ["## Soil-ordering, climate and crop contrasts", ""]
    judged = [f for f in group_findings if f.severity != "INFO"]
    infos = [f for f in group_findings if f.severity == "INFO"]
    if not judged:
        lines += ["No ordering or contrast violation.", ""]
    else:
        order = {"FAIL": 0, "WARN": 1}
        rows = sorted(
            judged, key=lambda f: (order.get(f.severity, 2), f.check, f.run_id)
        )
        lines += _md_table(
            ["severity", "check", "group", "value", "expected", "note"],
            [
                (f.severity, f.check, f.run_id, f.value, f.band, f.detail or f.source)
                for f in rows
            ],
        )
    if infos:
        lines += ["Informational contrasts:", ""]
        lines += _md_table(
            ["check", "group", "value", "known limitation"],
            [(f.check, f.run_id, f.value, f.known) for f in infos],
        )
    return lines


def _maturity_delta_cell(s: dict[str, Any]) -> str:
    if s.get("hot_maturity_lost") == 1.0:
        return "lost"
    delta = s.get("day_maturity_delta")
    return f"{delta:+.0f} d" if _finite(delta) else "n/a"


def _section_stress(results: list[RunResult]) -> list[str]:
    lines = [
        "## Stress responses (scenario / normal on the same crop, soil, climate, seed)",
        "",
    ]
    stress = [r for r in results if r.status == "ok" and r.spec.scenario != "normal"]
    if not stress:
        return [*lines, "No stress runs.", ""]
    for scenario in STRESS_SCENARIOS:
        rows = sorted(
            (r for r in stress if r.spec.scenario == scenario),
            key=lambda r: (r.spec.crop, r.spec.climate, r.spec.soil),
        )
        if not rows:
            continue
        lines += [f"### {scenario}", ""]
        table = []
        for r in rows:
            s = r.scalars
            n_fail = sum(
                1 for f in r.findings if f.category == "stress" and f.severity == "FAIL"
            )
            n_warn = sum(
                1 for f in r.findings if f.category == "stress" and f.severity == "WARN"
            )
            table.append(
                (
                    r.spec.crop,
                    CLIMATE_SHORT[r.spec.climate],
                    r.spec.soil,
                    s.get("agb_g_m2_rel", math.nan),
                    s.get("grain_g_m2_rel", math.nan),
                    s.get("et_actual_mm_rel", math.nan),
                    s.get("no3_leached_kg_ha_rel", math.nan),
                    s.get("deep_perc_mm_rel", math.nan),
                    _maturity_delta_cell(s),
                    f"F{n_fail} W{n_warn}",
                )
            )
        lines += _md_table(
            [
                "crop",
                "climate",
                "soil",
                "agb",
                "grain",
                "ETa",
                "NO3 leached",
                "deep perc",
                "maturity",
                "flags",
            ],
            table,
        )
    return lines


def _section_anchors(results: list[RunResult], checks: Sequence[Check]) -> list[str]:
    lines = [
        "## Regression anchors (loam_temperate, seed 42, realism-suite values)",
        "",
    ]
    anchors = [c for c in checks if c.category == "anchor"]
    ok_rows = _ok_scalars(results)
    by_run: dict[tuple[str, str], Finding] = {
        (f.run_id, f.check): f for r in results for f in r.findings
    }
    table = []
    for check in anchors:
        for s in ok_rows:
            if not check.applies(s):
                continue
            finding = by_run.get((s["run_id"], check.name))
            status = finding.severity if finding else "ok"
            table.append(
                (
                    check.name,
                    _fmt_band(check),
                    _cell(s.get(check.metric, math.nan)),
                    status,
                )
            )
    if not table:
        return [*lines, "No anchor row in this matrix.", ""]
    lines += _md_table(["anchor", "expected", "actual", "status"], table)
    return lines


def _stage_code(stage: Any) -> str:
    return str(stage)[:3]


def _section_matrices(results: list[RunResult]) -> list[str]:
    lines = ["## Per-crop matrices (normal weather)", ""]
    lines += [
        "Cell: above-ground biomass / grain (g/m2) / peak LAI, final stage, grade "
        "(P pass, W warn, F fail, E error, X expected for a crop not grown there).",
        "",
    ]
    normal = [r for r in results if r.spec.scenario == "normal"]
    soils = [s for s in ALL_SOILS if any(r.spec.soil == s for r in normal)]
    for crop in ALL_CROPS:
        crop_runs = [r for r in normal if r.spec.crop == crop]
        if not crop_runs:
            continue
        lines += [f"### {crop}", ""]
        table = []
        for climate in ALL_CLIMATES:
            row: list[Any] = [CLIMATE_SHORT[climate]]
            for soil in soils:
                r = next(
                    (
                        x
                        for x in crop_runs
                        if x.spec.climate == climate and x.spec.soil == soil
                    ),
                    None,
                )
                if r is None:
                    row.append("")
                elif r.status != "ok":
                    row.append("ERR")
                else:
                    s = r.scalars
                    agb, grain, lai = s["agb_g_m2"], s["grain_g_m2"], s["peak_lai"]
                    stage = _stage_code(s["final_stage"])
                    grade = GRADE_CODE.get(r.grade, "?")
                    row.append(f"{agb:.0f}/{grain:.0f}/{lai:.1f} {stage} {grade}")
            table.append(row)
        lines += _md_table(["climate", *soils], table)
    return lines


def _section_limitation(results: list[RunResult]) -> list[str]:
    lines = ["## Growth limitation (normal weather)", ""]
    lines += [
        "Cell: factor binding canopy growth on most days (n, p, s, fe, zn, mn, water, "
        "or none) : days it bound, and the season-mean growth factor "
        "(Liebig minimum of the nutrient stresses times water stress; 1 = unlimited).",
        "",
    ]
    normal = [r for r in results if r.spec.scenario == "normal" and r.status == "ok"]
    soils = [s for s in ALL_SOILS if any(r.spec.soil == s for r in normal)]
    table = []
    for climate in ALL_CLIMATES:
        for crop in ALL_CROPS:
            runs = [
                r for r in normal if r.spec.crop == crop and r.spec.climate == climate
            ]
            if not runs:
                continue
            row: list[Any] = [f"{crop} {CLIMATE_SHORT[climate]}"]
            for soil in soils:
                r = next((x for x in runs if x.spec.soil == soil), None)
                if r is None:
                    row.append("")
                    continue
                s = r.scalars
                row.append(
                    f"{s['binding_factor']}:{s['binding_factor_days']} "
                    f"({s['growth_factor_mean']:.2f})"
                )
            table.append(row)
    lines += _md_table(["crop climate", *soils], table)
    lines += [
        "Topsoil redox state and nutrient pools, averaged over the crops grown on "
        "each soil (normal weather). Anoxic = topsoil O2 below the anaerobic "
        "threshold; Fe max = highest plant-available Fe reached in the topsoil.",
        "",
    ]
    redox = []
    for soil in soils:
        for climate in ALL_CLIMATES:
            runs = [
                r for r in normal if r.spec.soil == soil and r.spec.climate == climate
            ]
            if not runs:
                continue

            def mean(key: str, rows: list[RunResult] = runs) -> float:
                return sum(float(x.scalars[key]) for x in rows) / len(rows)

            redox.append(
                (
                    soil,
                    CLIMATE_SHORT[climate],
                    round(mean("topsoil_anoxic_days")),
                    round(mean("anaerobic_layer_days")),
                    round(mean("topsoil_eh_min_mv")),
                    round(mean("fe_avail_0_start_ppm"), 1),
                    round(mean("fe_avail_0_max_ppm")),
                    round(mean("fe_toxic_days")),
                    round(mean("s_avail_start_kg_ha")),
                    round(mean("s_avail_end_kg_ha")),
                    round(mean("so4_leached_kg_ha")),
                    round(mean("stress_s_mean"), 2),
                )
            )
    lines += _md_table(
        [
            "soil",
            "climate",
            "anoxic d",
            "anaerobic layer-d",
            "Eh min mV",
            "Fe start ppm",
            "Fe max ppm",
            "Fe toxic d",
            "S start kg/ha",
            "S end kg/ha",
            "S leached kg/ha",
            "S stress mean",
        ],
        redox,
    )
    return lines


def _extreme(
    rows: Sequence[dict[str, Any]], key: str, *, absolute: bool = True
) -> tuple[float, str]:
    best, run_id = math.nan, ""
    for s in rows:
        value = s.get(key)
        if not _finite(value):
            continue
        magnitude = abs(value) if absolute else value
        if math.isnan(best) or magnitude > best:
            best, run_id = magnitude, s["run_id"]
    return best, run_id


def _section_balance(results: list[RunResult]) -> list[str]:
    rows = _ok_scalars(results)
    lines = ["## Mass balance and sanity", ""]
    if not rows:
        return [*lines, "No completed run.", ""]
    items = [
        ("max |water residual| (mm)", "water_residual_mm"),
        ("max |mineral-N ledger residual| (%)", "n_mineral_residual_pct"),
        ("max |ET-event minus water-module E+T| (mm)", "et_event_gap_mm"),
        (
            "max |tracked uptake minus plant-N gain| (kg N/ha)",
            "n_uptake_minus_plant_n_kg_ha",
        ),
        (
            "max potential NO3 mass-flow supply over uptake",
            "n_massflow_supply_over_uptake",
        ),
        ("max NH3 volatilisation, unfertilised (kg N/ha)", "volatilization_kg_ha"),
        ("max days theta outside [WP, saturation]", "theta_bound_violation_days"),
        ("max NaN count", "nan_count"),
        ("max negative pool count", "negative_pool_count"),
    ]
    table = []
    for label, key in items:
        value, run_id = _extreme(rows, key)
        table.append((label, value, run_id))
    lines += _md_table(["quantity", "value", "run"], table)
    return lines


def _section_known(findings: Sequence[Finding]) -> list[str]:
    lines = ["## Known limitations that fired", ""]
    known = [f for f in findings if f.known]
    if not known:
        return [*lines, "None.", ""]
    groups: dict[str, list[Finding]] = {}
    for f in known:
        groups.setdefault(f.known, []).append(f)
    table = []
    for text, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        checks = sorted({f.check for f in group})
        worst = (
            "FAIL" if any(f.severity == "FAIL" for f in group) else group[0].severity
        )
        table.append(
            (
                text,
                len(group),
                worst,
                ", ".join(checks[:4]) + (" ..." if len(checks) > 4 else ""),
            )
        )
    lines += _md_table(["limitation", "findings", "worst severity", "checks"], table)
    return lines


GLOSSARY: tuple[tuple[str, str], ...] = (
    ("agb_g_m2", "above-ground dry biomass at season end"),
    ("grain_g_m2 / harvest_index", "grain dry mass and grain / above-ground biomass"),
    ("hi_over_hi_max", "harvest index relative to the crop preset cap"),
    (
        "day_*",
        "days after sowing at which a phenological stage was entered (-1 = never)",
    ),
    (
        "water_stress_days",
        "days with canopy water-stress factor below 0.5 while LAI > 0.1",
    ),
    ("et_actual_mm", "soil evaporation plus transpiration taken from the water module"),
    ("et_over_et0 / t_over_et", "seasonal ETa/ET0 and transpiration share of ETa"),
    ("deep_perc_mm", "drainage out of the bottom layer"),
    (
        "water_residual_mm",
        "rain + irrigation - E - T - interception - runoff - deep percolation - "
        "dStorage",
    ),
    ("som_min_n_kg_ha", "net N mineralised from soil organic matter"),
    (
        "n_massflow_supply_kg_ha",
        "potential NO3 supply carried to the roots by transpiration mass flow "
        "(diagnostic; debits nothing)",
    ),
    (
        "n_mineral_residual_pct",
        "mineral-N ledger residual as % of gross mineral-N supply",
    ),
    (
        "mineral_n_peak_kg_ha / _drawdown",
        "profile NO3+NH4 peak and (min after peak) / peak",
    ),
    (
        "*_rel",
        "stress-scenario value / normal-scenario value on the same crop, soil, "
        "climate, seed",
    ),
    (
        "stress_<factor>_mean / binding_days_<factor>",
        "season-mean stress factor (1 = none) and days on which that factor was "
        "the Liebig minimum, for n, p, s, fe, zn, mn and water",
    ),
    (
        "binding_factor / growth_factor_mean",
        "factor binding growth on most days, and the season-mean product of the "
        "nutrient minimum and water stress the canopy applied",
    ),
    (
        "topsoil_anoxic_days / anaerobic_layer_days / topsoil_eh_min_mv",
        "days the topsoil O2 fraction sat below the anaerobic threshold, summed "
        "anaerobic layer-days over the profile, and the lowest topsoil redox "
        "potential",
    ),
    (
        "fe_toxic_days / fe_deficient_days / zn_deficient_days",
        "days topsoil available Fe exceeded the toxic level, or Fe / Zn sat below "
        "their critical levels; deficiency days are graded only on presets that "
        "are not meant to be deficient",
    ),
    (
        "s_avail_*_kg_ha",
        "plant-available sulfate over the whole profile at start, minimum and end",
    ),
    (
        "so4_leached_kg_ha",
        "sulfate-S drained out of the bottom of the profile over the season",
    ),
    (
        "grade",
        "ERROR > FAIL > WARN > PASS from run-scope findings; EXPECTED = clean "
        "not_grown run",
    ),
)


def _section_glossary() -> list[str]:
    lines = ["## Glossary", ""]
    lines += [f"- `{name}`: {text}" for name, text in GLOSSARY]
    lines.append("")
    return lines


def render_report(
    results: list[RunResult],
    group_findings: list[Finding],
    checks: Sequence[Check],
    notes: Sequence[str],
    total_runtime_s: float,
) -> str:
    sha, dirty = _git_info()
    n_normal = sum(1 for r in results if r.spec.scenario == "normal")
    lines = ["# Realism validation matrix", ""]
    n_stress = len(results) - n_normal
    dirty_note = " with a dirty working tree" if dirty else ""
    lines.append(
        f"Generated {datetime.now().isoformat(timespec='seconds')} on commit `{sha}`"
        f"{dirty_note}. {len(results)} runs ({n_normal} normal weather, "
        f"{n_stress} stress), {total_runtime_s:.0f} s wall clock, "
        f"{len(checks)} run-level checks."
    )
    lines.append("")
    lines += _md_table(
        ["grade", "runs"],
        [(g, sum(1 for r in results if r.grade == g)) for g in GRADE_ORDER],
    )
    if notes:
        lines += ["Notes:", "", *[f"- {n}" for n in notes], ""]
    run_findings = [f for r in results for f in r.findings]
    lines += _section_errors(results)
    lines += _section_by_check(
        "FAIL findings", [f for f in run_findings if f.severity == "FAIL"], 5
    )
    lines += _section_by_check(
        "WARN findings", [f for f in run_findings if f.severity == "WARN"], 0
    )
    lines += _section_allowed(run_findings)
    lines += _section_groups(group_findings)
    lines += _section_stress(results)
    lines += _section_anchors(results, checks)
    lines += _section_matrices(results)
    lines += _section_limitation(results)
    lines += _section_balance(results)
    lines += _section_known([*run_findings, *group_findings])
    lines += _section_glossary()
    return "\n".join(lines)


def write_outputs(
    out_dir: Path,
    results: list[RunResult],
    group_findings: list[Finding],
    checks: Sequence[Check],
    notes: Sequence[str],
    total_runtime_s: float,
    *,
    write_all_daily: bool,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "runs.csv", [r.scalars for r in results])
    findings = [*(f for r in results for f in r.findings), *group_findings]
    write_csv(out_dir / "findings.csv", [dict(vars(f)) for f in findings])
    daily_dir = out_dir / "daily"
    daily_dir.mkdir(exist_ok=True)
    for r in results:
        if r.daily and (write_all_daily or r.grade in ("FAIL", "ERROR")):
            write_csv(daily_dir / f"{r.spec.run_id}.csv", r.daily)
    (out_dir / "report.md").write_text(
        render_report(results, group_findings, checks, notes, total_runtime_s)
    )


def _ledger_plot(
    plt: Any,
    path: Path,
    runs: list[RunResult],
    climates: Sequence[str],
    components: Sequence[tuple[str, str]],
    reference: tuple[str, str],
    ylabel: str,
) -> None:
    fig, axes = plt.subplots(
        1, len(climates), figsize=(5 * len(climates), 4.5), sharey=True, squeeze=False
    )
    for ax, climate in zip(axes[0], climates, strict=True):
        rows = sorted(
            (r for r in runs if r.spec.climate == climate), key=lambda r: r.spec.soil
        )
        labels = [r.spec.soil for r in rows]
        bottoms = [0.0] * len(rows)
        for key, label in components:
            values = [float(r.scalars.get(key, 0.0) or 0.0) for r in rows]
            ax.bar(labels, values, bottom=bottoms, label=label)
            bottoms = [b + v for b, v in zip(bottoms, values, strict=True)]
        ref_key, ref_label = reference
        ax.plot(
            labels,
            [float(r.scalars.get(ref_key, 0.0) or 0.0) for r in rows],
            "k_",
            ms=14,
            label=ref_label,
        )
        ax.set_title(climate)
        ax.tick_params(axis="x", rotation=60, labelsize=7)
        ax.grid(axis="y", alpha=0.3)
    axes[0][0].set_ylabel(ylabel)
    axes[0][-1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _redox_plot(
    plt: Any, path: Path, runs: list[RunResult], climates: Sequence[str]
) -> Path:
    """Topsoil redox potential, plant-available Fe and biomass per soil.

    The reference lines are the redox potential below which the micronutrient
    module starts releasing sorbed Fe and the available-Fe level it treats as
    toxic; a drained soil should stay above the first and below the second.
    """
    fig, axes = plt.subplots(
        3, len(climates), figsize=(5 * len(climates), 9.5), squeeze=False
    )
    for col, climate in enumerate(climates):
        for r in sorted(runs, key=lambda r: r.spec.soil):
            if r.spec.climate != climate:
                continue
            days = _col(r.daily, "day_index")
            axes[0][col].plot(days, _col(r.daily, "eh_0_mv"), lw=1, label=r.spec.soil)
            axes[1][col].plot(days, _col(r.daily, "fe_avail_0_ppm"), lw=1)
            axes[2][col].plot(days, _col(r.daily, "agb_g_m2"), lw=1)
        axes[0][col].axhline(100.0, color="k", lw=0.8, ls="--")
        axes[1][col].axhline(TOXIC_FE_PPM, color="k", lw=0.8, ls="--")
        axes[1][col].set_yscale("symlog", linthresh=10.0)
        axes[0][col].set_title(f"maize - {climate}")
        axes[2][col].set_xlabel("days after sowing")
        for row in axes:
            row[col].grid(alpha=0.3)
    axes[0][0].set_ylabel("topsoil Eh (mV)")
    axes[1][0].set_ylabel("topsoil available Fe (ppm)")
    axes[2][0].set_ylabel("above-ground biomass (g/m2)")
    axes[0][-1].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def write_plots(out_dir: Path, results: list[RunResult]) -> list[Path]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(exist_ok=True)
    written: list[Path] = []
    normal = [r for r in results if r.status == "ok" and r.spec.scenario == "normal"]
    climates = [c for c in ALL_CLIMATES if any(r.spec.climate == c for r in normal)]
    if not climates:
        return written
    for crop in ALL_CROPS:
        crop_runs = [r for r in normal if r.spec.crop == crop]
        if not crop_runs:
            continue
        fig, axes = plt.subplots(
            2, len(climates), figsize=(5 * len(climates), 7), squeeze=False
        )
        for col, climate in enumerate(climates):
            for r in sorted(crop_runs, key=lambda r: r.spec.soil):
                if r.spec.climate != climate:
                    continue
                days = _col(r.daily, "day_index")
                axes[0][col].plot(
                    days, _col(r.daily, "agb_g_m2"), lw=1, label=r.spec.soil
                )
                axes[1][col].plot(days, _col(r.daily, "lai"), lw=1, label=r.spec.soil)
            axes[0][col].set_title(f"{crop} - {climate}")
            axes[1][col].set_xlabel("days after sowing")
            for ax in (axes[0][col], axes[1][col]):
                ax.grid(alpha=0.3)
        axes[0][0].set_ylabel("above-ground biomass (g/m2)")
        axes[1][0].set_ylabel("LAI")
        axes[0][-1].legend(fontsize=7)
        fig.tight_layout()
        path = plots_dir / f"trajectories_{crop}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)
    maize = [r for r in normal if r.spec.crop == "maize"]
    if maize:
        path = plots_dir / "maize_water_ledger.png"
        _ledger_plot(
            plt,
            path,
            maize,
            climates,
            [
                ("evap_mm", "evaporation"),
                ("transp_mm", "transpiration"),
                ("runoff_mm", "runoff"),
                ("deep_perc_mm", "deep percolation"),
            ],
            ("rain_mm", "rain"),
            "mm per season",
        )
        written.append(path)
        path = plots_dir / "maize_nitrogen_ledger.png"
        _ledger_plot(
            plt,
            path,
            maize,
            climates,
            [
                ("n_uptake_kg_ha", "plant uptake"),
                ("n_massflow_supply_kg_ha", "NO3 mass-flow supply (potential)"),
                ("no3_leached_kg_ha", "NO3 leached"),
                ("denitrification_kg_ha", "denitrified"),
                ("volatilization_kg_ha", "volatilised"),
            ],
            ("som_min_n_kg_ha", "net mineralisation"),
            "kg N/ha per season",
        )
        written.append(path)
        written.append(
            _redox_plot(plt, plots_dir / "maize_redox_iron.png", maize, climates)
        )
    stress = [
        r
        for r in results
        if r.status == "ok"
        and r.spec.scenario != "normal"
        and _finite(r.scalars.get("agb_g_m2_rel"))
    ]
    if stress:
        scenarios = [
            s for s in STRESS_SCENARIOS if any(r.spec.scenario == s for r in stress)
        ]
        fig, axes = plt.subplots(
            len(scenarios), 1, figsize=(12, 3.5 * len(scenarios)), squeeze=False
        )
        for ax, scenario in zip(axes[:, 0], scenarios, strict=True):
            rows = sorted(
                (r for r in stress if r.spec.scenario == scenario),
                key=lambda r: (r.spec.crop, r.spec.climate, r.spec.soil),
            )
            groups = sorted({(r.spec.crop, r.spec.climate) for r in rows})
            soils = sorted({r.spec.soil for r in rows})
            width = 0.8 / max(len(soils), 1)
            for j, soil in enumerate(soils):
                xs, ys = [], []
                for i, (crop, climate) in enumerate(groups):
                    r = next(
                        (
                            x
                            for x in rows
                            if x.spec.soil == soil
                            and (x.spec.crop, x.spec.climate) == (crop, climate)
                        ),
                        None,
                    )
                    if r is not None:
                        xs.append(i + j * width)
                        ys.append(r.scalars["agb_g_m2_rel"])
                ax.bar(xs, ys, width=width, label=soil)
            ax.axhline(1.0, color="k", lw=0.8)
            ax.set_xticks([i + width for i in range(len(groups))])
            ax.set_xticklabels(
                [f"{c}\n{CLIMATE_SHORT[k]}" for c, k in groups], fontsize=7
            )
            ax.set_ylabel(f"{scenario}: AGB / normal")
            ax.grid(axis="y", alpha=0.3)
        axes[0][0].legend(fontsize=7)
        fig.tight_layout()
        path = plots_dir / "stress_agb_rel.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        written.append(path)
    return written


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the crop x soil x climate realism matrix and grade it "
        "against literature bands.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--crops", nargs="+", default=list(ALL_CROPS), choices=ALL_CROPS
    )
    parser.add_argument(
        "--soils", nargs="+", default=list(ALL_SOILS), choices=ALL_SOILS
    )
    parser.add_argument(
        "--climates", nargs="+", default=list(ALL_CLIMATES), choices=ALL_CLIMATES
    )
    parser.add_argument(
        "--scenarios",
        nargs="+",
        default=list(STRESS_SCENARIOS),
        choices=STRESS_SCENARIOS,
        help="weather stress scenarios run on the stress subset",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[DEFAULT_SEED])
    parser.add_argument(
        "--no-stress-matrix", action="store_true", help="normal weather only"
    )
    parser.add_argument(
        "--sowing",
        type=date.fromisoformat,
        default=None,
        help="sowing date for every run (ISO)",
    )
    parser.add_argument(
        "--days", type=int, default=None, help="season length for every run"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--tag",
        default=None,
        help="output sub-directory (default: timestamp and commit)",
    )
    parser.add_argument(
        "--daily",
        action="store_true",
        help="write daily traces for every run, not only FAIL/ERROR",
    )
    parser.add_argument(
        "--plots", action="store_true", help="write PNG plots (needs matplotlib)"
    )
    parser.add_argument(
        "--fail-on",
        choices=("never", "fail", "warn"),
        default="never",
        help="exit status 1 threshold",
    )
    parser.add_argument(
        "--list", action="store_true", help="print the run specs and exit"
    )
    return parser.parse_args(argv)


def _print_specs(specs: Sequence[RunSpec]) -> None:
    for spec in specs:
        print(
            f"{spec.run_id:<72} sow {spec.sowing_date.isoformat()} {spec.days:>4} d  "
            f"{spec.fit}"
        )
    n_normal = sum(1 for s in specs if s.scenario == "normal")
    print(f"{len(specs)} runs ({n_normal} normal, {len(specs) - n_normal} stress)")


def run_matrix(
    specs: Sequence[RunSpec], libs: Libraries
) -> tuple[list[RunResult], list[str]]:
    """Run every spec. A handler exception under the strict event bus is retried
    with the lenient bus once; if that succeeds the rest of the matrix runs
    leniently and the report says so."""
    notes: list[str] = []
    debug_bus = True
    results: list[RunResult] = []
    for i, spec in enumerate(specs, 1):
        result = run_one(spec, libs, debug_bus=debug_bus)
        if result.status == "error" and debug_bus:
            retry = run_one(spec, libs, debug_bus=False)
            if retry.status == "ok":
                notes.append(
                    f"{spec.run_id} raised inside an event handler under "
                    "EventBus(debug_mode=True) "
                    f"({result.error}); the matrix continued with debug_mode=False, "
                    "which logs and "
                    "swallows handler exceptions."
                )
                debug_bus = False
                result = retry
        results.append(result)
        if i % 20 == 0 or i == len(specs):
            print(f"  {i}/{len(specs)} runs", file=sys.stderr, flush=True)
    return results, notes


def _point_latest(base: Path, target: Path) -> None:
    link = base / "latest"
    if link.is_symlink():
        link.unlink()
    elif link.exists():
        print(f"not replacing {link}: it is not a symlink", file=sys.stderr)
        return
    link.symlink_to(target.name, target_is_directory=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    specs = build_matrix(
        args.crops,
        args.soils,
        args.climates,
        args.scenarios,
        args.seeds,
        not args.no_stress_matrix,
        args.sowing,
        args.days,
    )
    if args.list:
        _print_specs(specs)
        return 0
    libs = load_libraries()
    checks = build_checks()
    t0 = time.perf_counter()
    results, notes = run_matrix(specs, libs)
    group_findings = evaluate_all(results, checks)
    total_runtime_s = time.perf_counter() - t0
    sha, _ = _git_info()
    tag = args.tag or f"{datetime.now():%Y%m%d-%H%M%S}-{sha}"
    out_dir = args.out / tag
    write_outputs(
        out_dir,
        results,
        group_findings,
        checks,
        notes,
        total_runtime_s,
        write_all_daily=args.daily,
    )
    plots = write_plots(out_dir, results) if args.plots else []
    _point_latest(args.out, out_dir)

    counts = {g: sum(1 for r in results if r.grade == g) for g in GRADE_ORDER}
    print(
        f"{len(results)} runs in {total_runtime_s:.0f} s: "
        + ", ".join(f"{g} {n}" for g, n in counts.items())
    )
    fails = _by_check([f for r in results for f in r.findings if f.severity == "FAIL"])
    for name, group in list(fails.items())[:15]:
        print(f"  FAIL {name}: {len(group)} runs")
    group_fail = sum(1 for f in group_findings if f.severity == "FAIL")
    group_warn = sum(1 for f in group_findings if f.severity == "WARN")
    print(f"  ordering/contrast findings: {group_fail} FAIL, {group_warn} WARN")
    print(f"report: {out_dir / 'report.md'}")
    if plots:
        print(f"plots: {len(plots)} files in {out_dir / 'plots'}")

    worst = {"never": (), "fail": ("ERROR", "FAIL"), "warn": ("ERROR", "FAIL", "WARN")}[
        args.fail_on
    ]
    return 1 if any(r.grade in worst for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
