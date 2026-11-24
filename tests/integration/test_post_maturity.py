"""A mature crop left standing stops acting on the soil (#539).

After physiological maturity the root front stops, and N, P, S, Fe, Zn and Mn
uptake stop (CERES-Maize ISTAGE gating; APSIM NG ``RootFrontVelocity``; WOFOST
``DVS_NPK_STOP``). Root turnover continues (APSIM NG ``Root.cs``) and water
uptake is not gated: transpiration follows green LAI (FAO-56 late season).

Engine path as ``test_realism._run_scenario``, seeds 42-51. Day *m* is the
first step after which the phenology stage is MATURITY; every assertion covers
days m+1..m+100. A save continuation across maturity covers #577/#585.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from agrogame.atmosphere.et.events import EvapotranspirationComputed
from agrogame.game.field import FieldManager, Patch, PatchConfig
from agrogame.params.phenology import PhenologyStage
from agrogame.plant.events import NutrientStressComputed, PlantNUptakeComputed
from agrogame.plant.presets import load_crop_presets
from agrogame.plant.roots.events import RootDepthChanged, RootTurnoverOccurred
from agrogame.sim.orchestrator import FullSimulationOrchestrator as Orch
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

SEEDS = range(42, 52)
STANDING_DAYS = 100
WEATHER_DAYS = 330  # Kenya maize matures on day 170-178 at seeds 42-51
# (crop, climate, soil, sowing date), as specified in #539 AC5.
SCENARIOS = {
    "kenya_maize": ("maize", "kenya_highlands", "loam_temperate", date(2024, 3, 1)),
    "nl_spring_wheat": (
        "spring_wheat",
        "netherlands_temperate",
        "clay_netherlands",
        date(2024, 4, 1),
    ),
}
_NON_N = frozenset({"p", "s", "fe", "zn", "mn"})


@cache
def _weather(climate_key: str, start: date, seed: int) -> tuple[WeatherRecord, ...]:
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        climate_key
    ]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    return tuple(gen.generate(WEATHER_DAYS, start).records)


def _drive(rec: WeatherRecord) -> dict[str, Any]:
    return {
        "drivers": DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
        "tmin_c": rec.tmin_c,
        "tmax_c": rec.tmax_c,
        "shortwave_mj_m2": rec.shortwave_mj_m2 or 12.0,
        "sim_date": rec.day,
    }


@dataclass
class _Day:
    """End-of-day state and the day's event tallies."""

    stage: PhenologyStage = PhenologyStage.PLANTED
    depth_cm: float = 0.0
    root_biomass: float = 0.0
    fractions: list[float] = field(default_factory=list)
    n_stock: float = 0.0
    shoot: float = 0.0
    grain: float = 0.0
    depth_events: int = 0
    turnover_events: int = 0
    n_uptake: float = 0.0
    non_n_uptake: float = 0.0
    nutrients: set[str] = field(default_factory=set)
    transpiration_mm: float = 0.0


class _Tally:
    """Per-day event sums, subscribed after every runtime on the bus."""

    def __init__(self, orch: Orch) -> None:
        self.day = _Day()
        bus = orch.event_bus
        bus.subscribe(RootDepthChanged, self._depth)
        bus.subscribe(RootTurnoverOccurred, self._turnover)
        bus.subscribe(PlantNUptakeComputed, self._n)
        bus.subscribe(NutrientStressComputed, self._non_n)
        bus.subscribe(EvapotranspirationComputed, self._et)

    def _depth(self, _ev: RootDepthChanged) -> None:
        self.day.depth_events += 1

    def _turnover(self, _ev: RootTurnoverOccurred) -> None:
        self.day.turnover_events += 1

    def _n(self, ev: PlantNUptakeComputed) -> None:
        self.day.n_uptake += ev.uptake_kg_ha

    def _non_n(self, ev: NutrientStressComputed) -> None:
        if ev.nutrient.lower() in _NON_N:
            self.day.non_n_uptake += ev.uptake_kg_ha
            self.day.nutrients.add(ev.nutrient.lower())

    def _et(self, ev: EvapotranspirationComputed) -> None:
        self.day.transpiration_mm += ev.transpiration_mm


def _snapshot(orch: Orch, tally: _Tally) -> _Day:
    day = tally.day
    day.stage = orch.phenology.state.stage
    day.depth_cm = orch.root_state.current_depth_cm
    day.root_biomass = orch.root_state.biomass_g_m2
    day.fractions = list(orch.root_state.layer_fractions or [])
    day.n_stock = orch.plant_n_stock_kg_ha
    day.shoot = orch.canopy.state.biomass_g_m2
    day.grain = orch.canopy.state.grain_biomass_g_m2
    return day


def _orch(scenario: str) -> Orch:
    crop_key, climate_key, soil_key, _start = SCENARIOS[scenario]
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        climate_key
    ]
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        crop_key, climate_key
    )
    profile = load_soil_presets(Path("soils/presets.yaml")).soils[soil_key]
    return Orch(profile, crop=crop, latitude_deg=climate.latitude_deg)


def _days(orch: Orch, scenario: str, seed: int) -> Iterator[_Day]:
    """Step the engine path (``test_realism._run_scenario``), day by day."""
    _crop, climate_key, _soil, start = SCENARIOS[scenario]
    tally = _Tally(orch)
    for rec in _weather(climate_key, start, seed):
        tally.day = _Day()
        orch.step_day(**_drive(rec))
        yield _snapshot(orch, tally)


@cache
def _standing(scenario: str, seed: int) -> tuple[list[_Day], list[_Day], float]:
    """Days 1..m, the 100 standing days after m, and the root turnover rate."""
    orch = _orch(scenario)
    season: list[_Day] = []
    standing: list[_Day] = []
    for day in _days(orch, scenario, seed):
        mature = bool(season) and season[-1].stage is PhenologyStage.MATURITY
        (standing if mature else season).append(day)
        if len(standing) == STANDING_DAYS:
            return season, standing, orch.roots.params.turnover_rate_per_day
    raise ValueError(f"{scenario} seed {seed}: no maturity + {STANDING_DAYS} days")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_standing_crop_stops_roots_and_nutrient_uptake(
    scenario: str, seed: int
) -> None:
    """#539 AC5 (a)-(f) and AC3 on every standing day m+1..m+100."""
    season, standing, turnover_rate = _standing(scenario, seed)
    at_m = season[-1]
    assert at_m.stage is PhenologyStage.MATURITY
    assert season[-2].stage is not PhenologyStage.MATURITY
    # The tallies observe a growing crop, so the zeros below are not vacuous.
    assert sum(d.n_uptake for d in season) > 0.0
    assert sum(d.non_n_uptake for d in season) > 0.0
    assert set().union(*(d.nutrients for d in season)) == _NON_N
    assert sum(d.depth_events for d in season) > 0
    prev = at_m
    for d in standing:
        assert d.stage is PhenologyStage.MATURITY
        # (a) the root front stops; nothing reports a depth change.
        assert d.depth_cm == at_m.depth_cm
        assert d.depth_events == 0
        # (b) no N uptake; the shoot N stock holds.
        assert d.n_uptake == 0.0
        assert d.n_stock == at_m.n_stock
        # (c) no P, S, Fe, Zn or Mn uptake.
        assert d.non_n_uptake == 0.0
        # (d) shoot and grain stay frozen (#433).
        assert (d.shoot, d.grain) == (at_m.shoot, at_m.grain)
        # (e) and AC3: turnover continues geometrically; the distribution freezes.
        assert d.root_biomass == pytest.approx(
            prev.root_biomass * (1.0 - turnover_rate), rel=1e-9
        )
        assert d.turnover_events == 1
        assert d.fractions == at_m.fractions
        prev = d
    # (f) water is not gated: the senescing canopy still transpires.
    assert sum(d.transpiration_mm for d in standing) > 0.0


# --- AC6: save continuation across maturity (#577/#585) ----------------------

_SAVE_AFTER_MATURITY = 10
_CONTINUE = 50


def _kenya_maize_manager() -> FieldManager:
    fm = FieldManager()
    fm.add_field("f1", [PatchConfig("loam_temperate", "maize", "kenya_highlands", 1.0)])
    return fm


def _continuation_state(fm: FieldManager) -> dict[str, Any]:
    orch = fm.fields["f1"].patches[0].orch
    return {
        "depth": orch.root_state.current_depth_cm,
        "root_biomass": orch.root_state.biomass_g_m2,
        "fractions": list(orch.root_state.layer_fractions or []),
        "n_stock": orch.plant_n_state.n_stock_kg_ha,
        "no3": list(orch.n_state.no3),
        "nh4": list(orch.n_state.nh4),
        "theta": list(orch.water_state.theta),
        "fe_available": list(orch.micro_state.fe_available),
    }


def test_save_after_maturity_continues_exactly() -> None:
    """#539 AC6: a save 10 days after maturity reloads into the same run."""
    records = _weather("kenya_highlands", date(2024, 3, 1), 42)
    ref = _kenya_maize_manager()
    orch = ref.fields["f1"].patches[0].orch
    day = 0
    while orch.phenology.state.stage is not PhenologyStage.MATURITY:
        ref.step_day(**_drive(records[day]))
        day += 1
    for rec in records[day : day + _SAVE_AFTER_MATURITY]:
        ref.step_day(**_drive(rec))
    day += _SAVE_AFTER_MATURITY
    saved = json.loads(json.dumps(ref.to_dict()))
    loaded = FieldManager.from_dict(saved)
    assert _continuation_state(loaded) == _continuation_state(ref)
    for rec in records[day : day + _CONTINUE]:
        ref.step_day(**_drive(rec))
        loaded.step_day(**_drive(rec))
    assert _continuation_state(loaded) == _continuation_state(ref)
    assert loaded.fields["f1"].patches[0].orch.phenology.state.stage is (
        PhenologyStage.MATURITY
    )


# --- AC10: the forecast drops the crop-uptake sink for a mature anchor ---------


def test_projection_inputs_turn_crop_uptake_off_at_maturity() -> None:
    """#539 AC10: off for a MATURITY anchor, on for a GRAIN_FILL anchor."""
    from agrogame.api.routes import _projection_inputs

    patch = Patch(PatchConfig("loam_temperate", "maize", "kenya_highlands", 1.0))
    seen: dict[PhenologyStage, bool] = {}
    for rec in _weather("kenya_highlands", date(2024, 3, 1), 42):
        patch.step_day(**_drive(rec))
        stage = patch.orch.phenology.state.stage
        if stage in (PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY):
            seen.setdefault(stage, _projection_inputs(patch).crop_n_uptake)
        if stage is PhenologyStage.MATURITY:
            break
    assert seen == {PhenologyStage.GRAIN_FILL: True, PhenologyStage.MATURITY: False}
