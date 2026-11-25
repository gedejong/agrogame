"""A mature crop left standing stops acting on the soil (#539, #623).

After physiological maturity the root front stops, and N, P, S, Fe, Zn and Mn
uptake stop (CERES-Maize ISTAGE gating; APSIM NG ``RootFrontVelocity``; WOFOST
``DVS_NPK_STOP``). Root turnover continues (APSIM NG ``Root.cs``). A
determinate crop carries no green leaf from its first MATURITY canopy step, so
it transpires nothing while it stands (#623: WOFOST ``crop_finish``, DSSAT
``IHARI = 'M'``, CERES-Wheat LSPHE, FAO-56 Kcb_end); grape keeps its leaves
until leaf drop (FAO-56 Table 12, footnote 18).

Engine path as ``test_realism._run_scenario``, seeds 42-51. Day *m* is the
first step after which the phenology stage is MATURITY; every assertion covers
days m+1..m+100. A save continuation across maturity covers #577/#585.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from itertools import pairwise
from dataclasses import dataclass, field, replace
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
from agrogame.soil.canopy.events import LAIUpdated
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
# #623 AC2 adds Sahel maize, the largest standing-crop water user (refinement).
_SEASON_SCENARIOS = {
    **SCENARIOS,
    "sahel_maize": ("maize", "sahel_arid", "loam_temperate", date(2024, 6, 1)),
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
    evaporation_mm: float = 0.0
    lai: float = 0.0
    lai_updates: list[tuple[float, float]] = field(default_factory=list)


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
        bus.subscribe(LAIUpdated, self._lai)

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
        self.day.evaporation_mm += ev.evaporation_mm

    def _lai(self, ev: LAIUpdated) -> None:
        self.day.lai_updates.append((ev.previous_lai, ev.new_lai))


def _snapshot(orch: Orch, tally: _Tally) -> _Day:
    day = tally.day
    day.stage = orch.phenology.state.stage
    day.depth_cm = orch.root_state.current_depth_cm
    day.root_biomass = orch.root_state.biomass_g_m2
    day.fractions = list(orch.root_state.layer_fractions or [])
    day.n_stock = orch.plant_n_stock_kg_ha
    day.shoot = orch.canopy.state.biomass_g_m2
    day.grain = orch.canopy.state.grain_biomass_g_m2
    day.lai = orch.canopy.state.lai
    return day


def _orch(scenario: str, *, keep_green: bool = False) -> Orch:
    """The scenario's engine; ``keep_green`` restores the pre-#623 canopy rule."""
    crop_key, climate_key, soil_key, _start = _SEASON_SCENARIOS[scenario]
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        climate_key
    ]
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        crop_key, climate_key
    )
    if keep_green:
        canopy = replace(crop.canopy, green_leaf_dies_at_maturity=False)
        crop = replace(crop, canopy=canopy)
    profile = load_soil_presets(Path("soils/presets.yaml")).soils[soil_key]
    return Orch(profile, crop=crop, latitude_deg=climate.latitude_deg)


def _days(orch: Orch, scenario: str, seed: int) -> Iterator[_Day]:
    """Step the engine path (``test_realism._run_scenario``), day by day."""
    _crop, climate_key, _soil, start = _SEASON_SCENARIOS[scenario]
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
    """#539 AC5 (a)-(e) and AC3, and #623 AC1/AC3, on every day m+1..m+100."""
    season, standing, turnover_rate = _standing(scenario, seed)
    at_m = season[-1]
    assert at_m.stage is PhenologyStage.MATURITY
    assert season[-2].stage is not PhenologyStage.MATURITY
    # The tallies observe a growing crop, so the zeros below are not vacuous.
    assert sum(d.n_uptake for d in season) > 0.0
    assert sum(d.non_n_uptake for d in season) > 0.0
    assert set().union(*(d.nutrients for d in season)) == _NON_N
    assert sum(d.depth_events for d in season) > 0
    assert sum(d.transpiration_mm for d in season) > 0.0
    # #623 AC1: the first MATURITY canopy step drops all green leaf, and the
    # canopy reports it.
    assert at_m.lai == 0.0
    assert len(at_m.lai_updates) == 1
    assert at_m.lai_updates[0][0] > 0.0
    assert at_m.lai_updates[0][1] == 0.0
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
        # (f), replaced by #623 AC3: no green leaf, so no transpiration.
        assert (d.lai, d.lai_updates, d.transpiration_mm) == (0.0, [], 0.0)
        prev = d
    # The bare soil still evaporates, so the ET tally is live.
    assert sum(d.evaporation_mm for d in standing) > 0.0


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("scenario", sorted(_SEASON_SCENARIOS))
def test_season_to_maturity_is_unchanged(scenario: str, seed: int) -> None:
    """#623 AC2: only day m's canopy step differs from the pre-#623 rule.

    Shoot, grain and transpiration agree on every day 1..m, and LAI on every
    day before m. The maturity day's own ET still reads the pre-maturity
    canopy, because ``et`` precedes ``canopy`` (ADR-010).
    """
    new = _standing(scenario, seed)[0]
    old: list[_Day] = []
    for day in _days(_orch(scenario, keep_green=True), scenario, seed):
        old.append(day)
        if day.stage is PhenologyStage.MATURITY:
            break
    assert len(old) == len(new)
    growth_new = [(d.shoot, d.grain, d.transpiration_mm) for d in new]
    assert growth_new == [(d.shoot, d.grain, d.transpiration_mm) for d in old]
    assert [d.lai for d in new[:-1]] == [d.lai for d in old[:-1]]
    assert new[-1].lai == 0.0 < old[-1].lai


def _patch_season(
    patch: Patch, records: Iterator[WeatherRecord], standing_days: int
) -> tuple[list[_Day], list[_Day]]:
    """Step a patch to maturity, then ``standing_days`` more: (grown, standing)."""
    tally = _Tally(patch.orch)
    grown: list[_Day] = []
    standing: list[_Day] = []
    while len(standing) < standing_days:
        tally.day = _Day()
        patch.step_day(**_drive(next(records)))
        day = _snapshot(patch.orch, tally)
        mature = bool(grown) and grown[-1].stage is PhenologyStage.MATURITY
        (standing if mature else grown).append(day)
    return grown, standing


def test_stop_lifts_for_the_next_crop() -> None:
    """The maturity stop belongs to the crop: a replanted crop roots and takes up.

    Kenya maize, seed 42: maturity + 10 standing days, harvest, 10 bare days,
    replant, then season 2 to maturity + 10 days. A gate that stayed engaged
    after replanting would starve every second season (review of #636). The
    #623 leaf drop belongs to the crop too: the replanted canopy grows again.
    """
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "kenya_highlands"
    ]
    maize = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", "kenya_highlands"
    )
    records = iter(
        SyntheticWeatherGenerator(climate, seed=42)
        .generate(500, date(2024, 3, 1))
        .records
    )
    patch = Patch(PatchConfig("loam_temperate", "maize", "kenya_highlands", 1.0))
    seasons = [_patch_season(patch, records, 10)]
    patch.harvest()
    patch.reset_crop(None)
    for _ in range(10):
        patch.step_day(**_drive(next(records)))
    patch.reset_crop(maize)
    assert patch.orch.phenology.state.stage is PhenologyStage.PLANTED
    replant_depth = patch.orch.root_state.current_depth_cm
    seasons.append(_patch_season(patch, records, 10))
    (grown_1, standing_1), (grown_2, standing_2) = seasons
    # #651 AC2: the front stops at the 100 cm loam bottom on every day of both
    # seasons, and both end there (DSSAT DEPMAX = DS(NLAYR); APSIM NG MaxDepth).
    bottom_cm = sum(layer.depth_cm for layer in patch.orch.profile.layers)
    assert bottom_cm == 100.0
    assert all(d.depth_cm <= bottom_cm for d in (*grown_1, *standing_1))
    assert all(d.depth_cm <= bottom_cm for d in (*grown_2, *standing_2))
    assert grown_1[-1].depth_cm == grown_2[-1].depth_cm == bottom_cm
    # Season 2 roots and takes up like season 1, within a factor of two.
    gain_1 = grown_1[-1].depth_cm - grown_1[0].depth_cm
    assert grown_2[-1].depth_cm - replant_depth > 0.5 * gain_1
    # #651 AC4 replaces "> 0.5 * len(grown_2)", which held only while the
    # front ran on to the crop's 150 cm below a 100 cm profile. Once the front
    # reaches the bottom it stops reporting, so compare against season 1.
    events_1 = sum(d.depth_events for d in grown_1)
    assert sum(d.depth_events for d in grown_2) > 0.5 * events_1
    for uptake in ("n_uptake", "non_n_uptake"):
        season_1 = sum(getattr(d, uptake) for d in grown_1)
        assert sum(getattr(d, uptake) for d in grown_2) > 0.5 * season_1, uptake
    assert set().union(*(d.nutrients for d in grown_2)) == _NON_N
    # And the stop re-engages at the second maturity.
    for d in standing_2:
        assert (d.depth_cm, d.depth_events) == (grown_2[-1].depth_cm, 0)
        assert d.n_uptake == d.non_n_uptake == 0.0
    # #623: the replanted canopy grows like the first (seed 42 peaks 3.47 and
    # 2.41), and each crop drops its green leaf at its own maturity.
    assert max(d.lai for d in grown_2) > 0.5 * max(d.lai for d in grown_1)
    for grown, standing in seasons:
        assert grown[-1].lai == 0.0
        assert all((d.lai, d.transpiration_mm) == (0.0, 0.0) for d in standing)


def test_grape_keeps_its_leaves_after_maturity_across_two_seasons() -> None:
    """#623 AC4: the exempt grape stays green and transpires while it stands.

    Kenya-highland grape, seed 42, loam, 1 Mar: maturity + 30 standing days,
    harvest, 10 bare days, replant, then season 2 to maturity + 30 days.
    FAO-56 Table 12, footnote 18: a deciduous perennial keeps its leaves until
    leaf drop, so senescence runs on at the pre-#623 peak rate.
    """
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "kenya_highlands"
    ]
    grape = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "grape", "kenya_highlands"
    )
    assert grape.canopy.green_leaf_dies_at_maturity is False
    records = iter(
        SyntheticWeatherGenerator(climate, seed=42)
        .generate(560, date(2024, 3, 1))
        .records
    )
    patch = Patch(PatchConfig("loam_temperate", "grape", "kenya_highlands", 1.0))
    seasons = [_patch_season(patch, records, 30)]
    patch.harvest()
    patch.reset_crop(None)
    for _ in range(10):
        patch.step_day(**_drive(next(records)))
    patch.reset_crop(grape)
    seasons.append(_patch_season(patch, records, 30))
    for grown, standing in seasons:
        lai = [grown[-1].lai] + [d.lai for d in standing]
        assert all(0.0 < b < a for a, b in pairwise(lai))
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


def test_pre_623_save_with_a_green_mature_canopy_drops_its_leaf() -> None:
    """#623 AC5: a mature save from before #623 (LAI 1.5) is bare after one step.

    The gate reads the restored phenology stage, so it adds no runtime memory
    (#585). That first step's ET still reads the saved LAI, as a fresh run's
    maturity day does, because ``et`` precedes ``canopy`` (ADR-010). From the
    next day on nothing transpires.
    """
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
    canopy_state = saved["fields"]["f1"]["patches"][0]["canopy_state"]
    assert canopy_state["lai"] == 0.0
    canopy_state["lai"] = 1.5  # as a pre-#623 save would hold it
    loaded = FieldManager.from_dict(saved)
    l_orch = loaded.fields["f1"].patches[0].orch
    assert l_orch.canopy.state.lai == 1.5
    tally = _Tally(l_orch)
    days: list[_Day] = []
    for rec in records[day : day + 10]:
        tally.day = _Day()
        loaded.step_day(**_drive(rec))
        days.append(_snapshot(l_orch, tally))
    assert days[0].stage is PhenologyStage.MATURITY
    assert (days[0].lai, days[0].lai_updates[-1][1]) == (0.0, 0.0)
    for d in days[1:]:
        assert (d.lai, d.lai_updates, d.transpiration_mm) == (0.0, [], 0.0)


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


# --- #651: the front stops at the soil bottom; #539's stop still governs above it


def test_maturity_stop_governs_where_the_profile_cap_does_not_bind() -> None:
    """#651 AC3: Sahel sorghum on 110 cm sandy soil stops at maturity, not the bottom.

    Seed 42: the front last advances on day 77 and the crop is mature after
    day 78, at 75.6 cm (as on main); the crop maximum is 180 cm.
    """
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        "sahel_arid"
    ]
    crop = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "sorghum", "sahel_arid"
    )
    profile = load_soil_presets(Path("soils/presets.yaml")).soils["sandy_subsaharan"]
    orch = Orch(profile, crop=crop, latitude_deg=climate.latitude_deg)
    bottom_cm = sum(layer.depth_cm for layer in profile.layers)
    tally = _Tally(orch)
    days: list[_Day] = []
    for rec in _weather("sahel_arid", date(2024, 6, 1), 42)[:150]:
        tally.day = _Day()
        orch.step_day(**_drive(rec))
        days.append(_snapshot(orch, tally))
    m = next(i for i, d in enumerate(days) if d.stage is PhenologyStage.MATURITY)
    at_m = days[m]
    assert bottom_cm == 110.0
    assert days[m - 1].depth_events == 1
    assert at_m.depth_cm < bottom_cm < orch.roots.params.max_depth_cm
    for d in days[m + 1 :]:
        assert (d.depth_cm, d.depth_events) == (at_m.depth_cm, 0)


def test_stale_saved_depth_below_the_bottom_is_clamped() -> None:
    """#651 AC5: a pre-fix save holding 118.8 cm on 100 cm loam reads 100.0.

    The clamp emits one ``RootDepthChanged`` even at MATURITY, so the canopy's
    persisted drought-depth memory follows (FAO-56 TAW ∝ Zr, Eq. 82).
    """
    from agrogame.soil.canopy.runtime import CanopyRuntime

    orch = _orch("kenya_maize")
    records = iter(_weather("kenya_highlands", date(2024, 3, 1), 42))
    while orch.phenology.state.stage is not PhenologyStage.MATURITY:
        orch.step_day(**_drive(next(records)))
    canopy_rt = next(rt for rt in orch._runtimes if isinstance(rt, CanopyRuntime))
    orch.root_state.current_depth_cm = 118.8
    canopy_rt._root_depth_cm = 118.8
    assert canopy_rt._drought_depth_factor() == pytest.approx(40.0 / 118.8)
    events: list[RootDepthChanged] = []
    orch.event_bus.subscribe(RootDepthChanged, events.append)
    orch.step_day(**_drive(next(records)))
    assert orch.root_state.current_depth_cm == 100.0
    assert canopy_rt._drought_depth_factor() == pytest.approx(0.40)
    assert [(e.previous_cm, e.new_cm) for e in events] == [(118.8, 100.0)]
