"""Biopores drive no simulated flux: 0 and 500 /m² give identical outputs (#524).

This test pins the **absence** of a coupling, deliberately. Biopores form,
decay and donate volume into the reported macropore pool (ADR-009, ADR-010),
but nothing simulated reads that pool: gas diffusion uses total porosity,
which the donation conserves, and the Ksat factor follows aggregation, not
the pore network (ADR-016). Any future coupling, such as root penetration
through biopores or #485's preferential flow, must replace this test with a
test of that coupling rather than loosen it.

Scenario (#524 refinement): maize x netherlands_temperate on loam_temperate
and clay_temperate, two 150-day seasons (seeds 42 and 43) joined by
``reset_crop``, 150 kg N/ha ammonium nitrate at each sowing. Biopore density
is pinned on every layer before every ``step_day``, at 0 and at the
``BioporeParams.max_density_per_m2`` cap of 500 /m² (Pierret et al. 2007).
"""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path

import pytest

from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator as Orch
from agrogame.soil.biopores.params import BioporeParams
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.soil.water.events import RunoffGenerated, WaterDrained
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import ClimatePreset, load_climate_presets

_CLIMATE = "netherlands_temperate"
_SEASONS = ((42, 2024), (43, 2025))  # (weather seed, sowing year)
_SEASON_DAYS = 150
_N_KG_HA = 150.0
_PINNED = (0.0, BioporeParams().max_density_per_m2)
_ABS_TOL = 1e-9
_REL_TOL_GAS = 1e-12
_MIN_MACRO_SHIFT = 1e-3  # 500 /m² x π (1 mm)² = 0.00157 m³/m³ donated
_EXACT = (
    "theta no3 nh4 eh microsite root_depth root_biomass biomass grain "
    "drainage runoff no3_leached"
).split()

Trace = dict[str, list[float]]


def _pin(orch: Orch, density: float) -> None:
    state = orch.biopore_state
    state.density_per_m2[:] = [density] * len(state.density_per_m2)
    state.recompute_volume_fraction()


def _record_day(orch: Orch, trace: Trace) -> None:
    gas, roots, canopy = orch.gas_state, orch.root_state, orch.canopy.state
    trace["theta"] += orch.water_state.theta
    trace["no3"] += orch.n_state.no3
    trace["nh4"] += orch.n_state.nh4
    trace["eh"] += orch.redox_state.eh_mv
    trace["microsite"] += gas.anaerobic_microsite_frac
    trace["o2"] += gas.o2_frac
    trace["co2"] += gas.co2_frac
    trace["root_depth"].append(roots.current_depth_cm)
    trace["root_biomass"].append(roots.biomass_g_m2)
    trace["biomass"].append(canopy.biomass_g_m2)
    trace["grain"].append(canopy.grain_biomass_g_m2)
    trace["macro0"].append(orch.pore_state.macro[0])


@cache
def _climate() -> ClimatePreset:
    return load_climate_presets(Path("data/climate/presets.yaml")).climates[_CLIMATE]


def _run_season(orch: Orch, seed: int, year: int, density: float, trace: Trace) -> None:
    totals = {"drainage": 0.0, "runoff": 0.0, "no3_leached": 0.0}

    def _drained(ev: WaterDrained) -> None:
        if ev.to_layer == -1:
            totals["drainage"] += ev.amount_mm

    def _runoff(ev: RunoffGenerated) -> None:
        totals["runoff"] += ev.amount_mm

    def _leached(ev: NutrientLeached) -> None:
        if ev.nutrient == "NO3":
            totals["no3_leached"] += ev.amount_kg_ha

    # reset_crop clears every subscription, so subscribe once per season.
    orch.event_bus.subscribe(WaterDrained, _drained)
    orch.event_bus.subscribe(RunoffGenerated, _runoff)
    orch.event_bus.subscribe(NutrientLeached, _leached)
    orch.apply_fertilizer("ammonium_nitrate", _N_KG_HA)
    weather = SyntheticWeatherGenerator(_climate(), seed=seed)
    for rec in weather.generate(_SEASON_DAYS, date(year, 4, 1)).records:
        _pin(orch, density)
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
        _record_day(orch, trace)
    for key, value in totals.items():
        trace[key].append(value)


@cache
def _two_seasons(soil_key: str, density: float) -> Trace:
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", _CLIMATE
    )
    profile = load_soil_presets(Path("data/soils/presets.yaml")).soils[soil_key]
    orch = Orch(profile, crop=crop, latitude_deg=_climate().latitude_deg)
    trace: Trace = {k: [] for k in [*_EXACT, "o2", "co2", "macro0"]}
    for i, (seed, year) in enumerate(_SEASONS):
        if i:
            orch.reset_crop(crop)
        _run_season(orch, seed, year, density, trace)
    return trace


_SOILS = pytest.mark.parametrize("soil_key", ["loam_temperate", "clay_temperate"])


@_SOILS
def test_pinned_biopores_reach_the_reported_macropore_pool(soil_key: str) -> None:
    """Non-vacuity: 500 /m² visibly enlarges ``pore_state.macro[0]`` every day."""
    bare, dense = (_two_seasons(soil_key, d)["macro0"] for d in _PINNED)
    assert len(bare) == len(_SEASONS) * _SEASON_DAYS
    shifts = [b - a for a, b in zip(bare, dense, strict=True)]
    assert min(shifts) >= _MIN_MACRO_SHIFT, min(shifts)


@_SOILS
def test_biopore_density_leaves_simulated_outputs_unchanged(soil_key: str) -> None:
    """Every simulated output is identical at 0 and 500 /m² across two seasons."""
    bare, dense = (_two_seasons(soil_key, d) for d in _PINNED)
    assert bare["root_depth"][-1] > 0.0 and sum(bare["drainage"]) > 0.0
    for key in _EXACT:
        assert dense[key] == pytest.approx(bare[key], rel=0.0, abs=_ABS_TOL), key
    for key in ("o2", "co2"):
        assert dense[key] == pytest.approx(bare[key], rel=_REL_TOL_GAS, abs=0.0), key
