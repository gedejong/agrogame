"""Soil pH has no relaxation toward a target (#481 PR A, ADR-020 (b)).

Before #481, ``SoilChemistryModule.daily_step`` pulled every layer 0.001/day
toward ``DayTick.target_ph`` (6.8). With the N-cycle proton budget of #492 that
spring capped acidification and undid lime. Now pH moves only with the proton
load and lime, so acidification accumulates with the N applied and lime
persists. The behaviour bounds below are the #481 refinement's (A4), from its
prototype of exactly this change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from datetime import date
from itertools import pairwise
from pathlib import Path

import pytest

from agrogame.plant.presets import CropPreset, load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.chemistry import ChemistryParams, SoilChemistryModule
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

_GOLDEN = Path(__file__).parents[1] / "fixtures" / "wiring_order_golden.json"
_CLIMATE = "netherlands_temperate"
_SOW = date(2024, 4, 25)
_HARVEST_DAY = 180
_YEARS = 5
_UREA_SPLIT = {0: 0.4, 30: 0.3, 60: 0.3}  # share of the season's N on that day
_LIME_KG_HA = 3000.0
_LIME_YEAR = 3


def _loam() -> SoilProfile:
    return load_soil_presets(Path("data/soils/presets.yaml")).soils["loam_temperate"]


def _maize() -> CropPreset:
    return load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", _CLIMATE
    )


def _chemistry_handlers(order: dict[str, list[str]], event: str) -> list[str]:
    return [h for h in order.get(event, []) if h.startswith("ChemistryRuntime.")]


def _live_order(orch: FullSimulationOrchestrator) -> dict[str, list[str]]:
    """Per-event handler ids, as ``tests/test_orchestrator_wiring.py`` names them."""
    out: dict[str, list[str]] = {}
    for etype, handlers in orch.event_bus._handlers.items():
        out[etype.__name__] = [
            f"{type(getattr(h, '__self__', None)).__name__}."
            f"{getattr(h, '__name__', repr(h))}"
            for h in handlers
        ]
    return out


# --- A1: precondition, the #492 proxies are gone ----------------------------


def test_precondition_ph_proxies_are_gone() -> None:
    """A1: without #492 removing the relaxation lets the -0.30/season clock run.

    Measured in the #481 refinement: 6.07 / 5.34 / 4.61 / 4.00 / 4.00.
    """
    assert not hasattr(SoilChemistryModule, "apply_phosphorus_fixation")
    assert not hasattr(SoilChemistryModule, "apply_nutrient_leaching")
    param_names = {f.name for f in fields(ChemistryParams)}
    assert not param_names & {"p_fixation_ph_delta", "no3_leach_ph_delta"}

    golden = json.loads(_GOLDEN.read_text())
    orch = FullSimulationOrchestrator(_loam(), crop=_maize())
    fresh = _live_order(orch)
    orch.reset_crop(_maize())
    for order in (golden, fresh, _live_order(orch)):
        for event in ("NutrientLeached", "PhosphorusFixationOccurred"):
            assert _chemistry_handlers(order, event) == [], event


# --- A2: no relaxation --------------------------------------------------------


def test_relaxation_params_are_gone() -> None:
    """A2: ``buffering_rate`` and ``default_target_ph`` are deleted."""
    param_names = {f.name for f in fields(ChemistryParams)}
    assert not param_names & {"buffering_rate", "default_target_ph"}


def test_target_ph_does_not_move_soil_ph() -> None:
    """A2: ``step_day(target_ph=...)`` no longer drives soil pH.

    Measured on main before #481: ten days toward 4.5 or 8.5 left layer 0
    0.023 lower and 0.017 higher than ten days toward 6.8.
    """
    runs: list[list[float]] = []
    for target in (4.5, 8.5):
        orch = FullSimulationOrchestrator(_loam(), crop=_maize(), latitude_deg=52.0)
        for day in range(10):
            orch.step_day(
                DailyDrivers(rainfall_mm=2.0),
                tmin_c=10.0,
                tmax_c=22.0,
                shortwave_mj_m2=15.0,
                sim_date=date(2024, 5, 1 + day),
                target_ph=target,
            )
        runs.append(orch.chem.ph_by_layer)
    assert runs[0] == runs[1]


# --- A4: behaviour over five calendar years -----------------------------------


@dataclass(frozen=True)
class _Trajectory:
    """Layer-0 pH at the end of each 365-day year."""

    year_end_ph: list[float]


def _five_years(n_kg_ha: float, lime_kg_ha: float = 0.0) -> _Trajectory:
    """The #481 5-year harness: loam_temperate, maize, netherlands_temperate.

    365-day years from 25 April, seed 42. Sow on day 0 of each year; at day
    180 ``harvest()`` then ``reset_crop(None)`` to the next sowing. Urea
    40/30/30 % of ``n_kg_ha`` on days 0/30/60; lime on day 0 of year 3.
    """
    maize = _maize()
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[_CLIMATE]
    records = (
        SyntheticWeatherGenerator(climate, seed=42).generate(_YEARS * 365, _SOW).records
    )
    orch = FullSimulationOrchestrator(
        _loam(), crop=maize, latitude_deg=climate.latitude_deg
    )
    year_end: list[float] = []
    for year in range(_YEARS):
        for day in range(365):
            if day == 0 and year > 0:
                orch.harvest()  # a no-op on the bare default plant
                orch.reset_crop(maize)
            if day == _HARVEST_DAY:
                orch.harvest()
                orch.reset_crop(None)
            share = _UREA_SPLIT.get(day, 0.0)
            if n_kg_ha > 0.0 and share > 0.0:
                orch.apply_fertilizer("urea", n_kg_ha * share)
            if day == 0 and lime_kg_ha > 0.0 and year + 1 == _LIME_YEAR:
                orch.apply_lime(lime_kg_ha, 0)
            rec = records[year * 365 + day]
            orch.step_day(
                DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
        year_end.append(orch.chem.ph_by_layer[0])
    return _Trajectory(year_end)


@pytest.fixture(scope="module")
def trajectories() -> dict[str, _Trajectory]:
    """The three A4 runs, computed once; the table prints under ``-s``."""
    runs = {
        "200 kg N": _five_years(200.0),
        "0 kg N": _five_years(0.0),
        "200 kg N + 3 t lime yr 3": _five_years(200.0, lime_kg_ha=_LIME_KG_HA),
    }
    print("\nlayer-0 pH at year end, loam_temperate / maize / NL, seed 42")
    for name, run in runs.items():
        cells = " / ".join(f"{ph:.3f}" for ph in run.year_end_ph)
        print(f"  {name:<26} {cells}")
    return runs


def test_acidification_accumulates_with_n(
    trajectories: dict[str, _Trajectory],
) -> None:
    """A4(a): at 200 kg N pH falls every year, and keeps falling.

    Prototype: year 5 at 6.569, year-4 to year-5 decrement 0.047. With the
    relaxation the decrement had shrunk to 0.008 as pH neared its asymptote.
    """
    ph = trajectories["200 kg N"].year_end_ph
    assert all(a > b for a, b in pairwise(ph)), ph
    assert 6.52 <= ph[4] <= 6.62, ph
    assert ph[3] - ph[4] >= 0.035, ph


def test_no_n_no_drift_over_five_years(
    trajectories: dict[str, _Trajectory],
) -> None:
    """A4(b): at 0 kg N, |year-5 pH - 6.8| <= 0.01 (prototype 0.002)."""
    ph = trajectories["0 kg N"].year_end_ph
    assert abs(ph[4] - 6.8) <= 0.01, ph


def test_lime_persists(trajectories: dict[str, _Trajectory]) -> None:
    """A4(c): 3 t/ha lime in year 3 still lifts year-5 pH by >= 0.30.

    Prototype 0.353, the full lime step; with the relaxation it was 0.12.
    """
    limed = trajectories["200 kg N + 3 t lime yr 3"].year_end_ph
    unlimed = trajectories["200 kg N"].year_end_ph
    assert limed[4] - unlimed[4] >= 0.30, (limed, unlimed)
