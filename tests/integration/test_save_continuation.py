"""A mid-season load continues the same simulation exactly (#515, #577).

Default scenario (issue #515): one field of three maize patches under
``netherlands_temperate`` (sandy/loam/clay at 0.333/0.334/0.333), weather from
2024-04-01, urea 60 kg N/ha before day 1. A *save at day d* is
``FieldManager.to_dict()`` after d steps, a strict JSON round trip (no
``default=``), then ``FieldManager.from_dict()``.

Continuation is compared with ``==``, not a tolerance (#577). JSON round-trips
floats exactly, so once every piece of cross-day memory travels with the save
a loaded run is the uninterrupted run. The full-graph walk (:func:`_walk`) is
the guard that keeps it so: memory a new module holds outside the save shows
up there as a differing leaf.

Two weathers: (a) the shipped seeded generator, and (b) the same series with
temperature and shortwave replaced from De Bilt monthly normals, under which
the ET stage-2 clock mattered most (#560, #577).
"""

from __future__ import annotations

import copy
import dataclasses
import json
import math
import random
import types
from collections import deque
from datetime import date
from enum import Enum
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import Any

import pytest

from agrogame.atmosphere.et.runtime import ETRuntime
from agrogame.events.recorder import EventRecorder
from agrogame.game.field import FieldManager, PatchConfig
from agrogame.game.save import SCHEMA_VERSION
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.sim.orchestrator import FullSimulationOrchestrator as Orch
from agrogame.soil.aggregation.runtime import AggregationRuntime
from agrogame.soil.canopy.runtime import CanopyRuntime
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

_CLIMATE = "netherlands_temperate"
_SOILS = (
    ("sandy_temperate", "maize", 0.333),
    ("loam_temperate", "maize", 0.334),
    ("clay_temperate", "maize", 0.333),
)
SAVE_DAYS = (30, 60, 100, 130)
GUARD_DAYS = (60, 100)
SEASON = 150
# #515 AC8: every *State container reachable from the orchestrator. A new soil
# module (potassium #502, soil temperature #462, salinity #468) must be saved
# and added here, or the discovery assertion in the AC8 test fails.
_COMPARED = frozenset(
    "water_state n_state p_state s_state chem_state redox_state micro_state "
    "agg_state pore_state biopore_state gas_state microbes.state canopy.state "
    "phenology.state root_state plant_n_state".split()
)
# KNMI daily data, station 260 De Bilt (etmgeg_260): 1991-2020 monthly means
# of TN and TX (deg C) and Q/100 (MJ m-2 d-1), as in the #560 refinement.
# fmt: off
_DE_BILT_TMIN = (
    0.88, 0.73, 2.37, 4.52, 7.97, 10.83, 12.99, 12.51, 10.02, 7.09, 3.93, 1.55,
)
_DE_BILT_TMAX = (
    6.13, 7.03, 10.49, 14.84, 18.34, 20.93, 23.08, 22.88, 19.47, 14.83, 9.92, 6.66,
)
_DE_BILT_SW = (
    2.35, 4.58, 8.61, 14.14, 17.48, 18.37, 17.83, 15.14, 10.46, 6.06, 2.81, 1.74,
)
# fmt: on


@cache
def _weather(seed: int, year: int) -> tuple[WeatherRecord, ...]:
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[_CLIMATE]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    return tuple(gen.generate(SEASON, date(year, 4, 1)).records)


@cache
def _de_bilt_weather(seed: int, year: int) -> tuple[WeatherRecord, ...]:
    """Weather (a) with temperature and shortwave from De Bilt normals (#577)."""
    rng, out = random.Random(seed), []
    for rec in _weather(seed, year):
        m = rec.day.month - 1
        tmin = _DE_BILT_TMIN[m] + rng.gauss(0.0, 1.5)
        tmax = max(tmin + 1.0, _DE_BILT_TMAX[m] + rng.gauss(0.0, 1.5))
        sw = max(0.0, _DE_BILT_SW[m] + rng.gauss(0.0, 1.5))
        out.append(
            dataclasses.replace(rec, tmin_c=tmin, tmax_c=tmax, shortwave_mj_m2=sw)
        )
    return tuple(out)


WEATHERS = {"legacy": _weather, "de_bilt": _de_bilt_weather}


def _new_manager(patches: tuple[tuple[str, str, float], ...] = _SOILS) -> FieldManager:
    fm = FieldManager()
    configs = [PatchConfig(s, crop, _CLIMATE, a) for s, crop, a in patches]
    fm.add_field("f1", configs).apply_fertilizer("urea", 60.0)
    return fm


def _step(
    fm: FieldManager,
    start: int,
    end: int,
    seed: int = 42,
    year: int = 2024,
    weather: str = "legacy",
) -> None:
    for rec in WEATHERS[weather](seed, year)[start:end]:
        fm.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )


def _save(fm: FieldManager) -> dict[str, Any]:
    """Strict JSON round trip: a deque or dataclass in the payload raises (AC5)."""
    saved: dict[str, Any] = json.loads(json.dumps(fm.to_dict()))
    return saved


def _orchs(fm: FieldManager) -> list[Orch]:
    return [p.orch for p in fm.fields["f1"].patches]


def _runtime(orch: Orch, cls: type) -> Any:
    """The patch's runtime of class ``cls``, found among the bus subscribers."""
    return next(rt for rt in _bus_owners(orch) if type(rt) is cls)


def _som_pools(orch: Orch) -> list[float]:
    """Per-layer SOM pool C and N, interleaved (C, N, C, N, ...)."""
    pools = [
        p
        for ly in orch.som.state.layers
        for p in (ly.labile, ly.intermediate, ly.stable)
    ]
    return [v for p in pools for v in (p.c_kg_ha, p.n_kg_ha)]


def _end_values(fm: FieldManager) -> list[dict[str, float]]:
    return [
        {
            "grain": o.canopy.state.grain_biomass_g_m2,
            "agb": o.canopy.state.biomass_g_m2,
            "lai": o.canopy.state.lai,
            "shoot_n": o.plant_n_stock_kg_ha,
            "root": o.root_state.current_depth_cm,
            "som": sum(_som_pools(o)[0::2]),
            "no3": sum(o.n_state.no3),
        }
        for o in _orchs(fm)
    ]


def _assert_identical(loaded: list[dict], ref: list[dict], label: str) -> None:
    """Bit-identical end values; prints each patch's relative deltas."""
    for i, (got, want) in enumerate(zip(loaded, ref, strict=True)):
        rel = {k: f"{100 * (got[k] - want[k]) / (want[k] or 1.0):+.3f}%" for k in want}
        print(f"{label} patch {i}: {rel}")
    assert loaded == ref, label


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a):
        return math.isnan(b)
    return bool(a == b)


def _mismatches(got: dict[str, Any], want: dict[str, Any]) -> list[str]:
    keys = sorted(got.keys() | want.keys())
    return [
        f"{k}: {got.get(k, '<absent>')!r} != {want.get(k, '<absent>')!r}"
        for k in keys
        if k not in got or k not in want or not _same(got[k], want[k])
    ]


def _flat(value: Any, path: str) -> dict[str, Any]:
    """Flatten a container's public attributes to ``{path: scalar}``."""
    if isinstance(value, Enum):
        return {path: value.value}
    if isinstance(value, list | tuple):
        items: Any = enumerate(value)
    elif isinstance(value, dict) or hasattr(value, "__dict__"):
        attrs = value if isinstance(value, dict) else vars(value)
        items = ((k, v) for k, v in attrs.items() if not str(k).startswith("_"))
    else:
        return {path: value}
    return {p: v for k, item in items for p, v in _flat(item, f"{path}.{k}").items()}


def _state_view(orch: Orch) -> dict[str, Any]:
    view = {n: _flat(attrgetter(n)(orch), n) for n in sorted(_COMPARED)}
    view["som"] = _flat(_som_pools(orch), "som")
    view["plan"] = _flat(orch.management_plan.to_dict(), "plan")
    view["misc"] = {"day": orch.day_counter, "history": tuple(orch.crop_history)}
    return {p: v for part in view.values() for p, v in part.items()}


_WALK_SKIP_NAMES = frozenset({"event_bus", "params", "_params", "profile"})
_WALK_SKIP_TYPES = (
    types.FunctionType,
    types.MethodType,
    types.BuiltinFunctionType,
    types.ModuleType,
    type,
    EventRecorder,
)
_WALK_LEAVES = (type(None), bool, int, float, str, date, Enum)


def _bus_owners(orch: Orch) -> list[Any]:
    """Every object subscribed to the patch's bus (handlers' ``__self__``)."""
    handlers = [h for hs in orch.event_bus._handlers.values() for h in hs]
    owners = {id(h.__self__): h.__self__ for h in handlers if hasattr(h, "__self__")}
    return list(owners.values())


def _walk(orch: Orch) -> dict[str, Any]:
    """Full-graph walk (#577 AC2): every scalar leaf, private attributes included.

    Starts at the orchestrator and every bus subscriber and recurses through
    attributes, lists, tuples, dicts, deques (``maxlen`` and items) and sets.
    Each object is visited once, at its first path in sorted-attribute order,
    so a broken alias shows up as extra leaves.
    """
    leaves: dict[str, Any] = {}
    seen: set[int] = set()

    def visit(value: Any, path: str) -> None:
        if isinstance(value, _WALK_SKIP_TYPES):
            return
        if isinstance(value, _WALK_LEAVES):
            leaves[path] = value
            return
        if not isinstance(value, tuple | frozenset):
            if id(value) in seen:
                return
            seen.add(id(value))
        if isinstance(value, set | frozenset):
            leaves[path] = tuple(sorted(map(repr, value)))
            return
        if isinstance(value, deque):
            leaves[f"{path}.maxlen"] = value.maxlen
        if isinstance(value, list | tuple | deque):
            children: Any = ((f"[{i}]", v) for i, v in enumerate(value))
        elif isinstance(value, dict):
            children = ((f"[{k!r}]", value[k]) for k in sorted(value, key=repr))
        elif hasattr(value, "__dict__"):
            attrs = vars(value)
            names = sorted(k for k in attrs if k not in _WALK_SKIP_NAMES)
            children = ((f".{k}", attrs[k]) for k in names)
        else:
            leaves[path] = value
            return
        for suffix, child in children:
            visit(child, path + suffix)

    visit(orch, "orch")
    for i, owner in enumerate(_bus_owners(orch)):
        visit(owner, f"bus[{i}]:{type(owner).__name__}")
    return leaves


def _discover_states(orch: Orch) -> dict[int, str]:
    """Name each *State object reachable as ``orch.<attr>`` or ``orch.<attr>.state``."""
    public = [(k, v) for k, v in vars(orch).items() if not k.startswith("_")]
    found: dict[int, str] = {}
    for name, value in public:
        if type(value).__name__.endswith("State"):
            found.setdefault(id(value), name)
    for name, value in public:
        inner = getattr(value, "state", None)
        if type(inner).__name__.endswith("State"):
            found.setdefault(id(inner), f"{name}.state")
    return found


def _runtime_held_states(orch: Orch) -> list[tuple[str, Any]]:
    """Public *State attributes of every object subscribed to the patch's bus."""
    return [
        (f"{type(owner).__name__}.{attr}", value)
        for owner in _bus_owners(orch)
        for attr, value in vars(owner).items()
        if not attr.startswith("_") and type(value).__name__.endswith("State")
    ]


@pytest.fixture(scope="module", params=sorted(WEATHERS))
def runs(request: pytest.FixtureRequest) -> dict[str, Any]:
    """One uninterrupted default-scenario run, its saves and their continuations."""
    weather: str = request.param
    fm, saves, done = _new_manager(), {}, 0
    out: dict[str, Any] = {"weather": weather, "originals": {}, "graph_saved": {}}
    for day in SAVE_DAYS:
        _step(fm, done, day, weather=weather)
        done, saves[day] = day, _save(fm)
        out["graph_saved"][day] = [_walk(o) for o in _orchs(fm)]
        if day in GUARD_DAYS:
            out["originals"][day] = [_state_view(o) for o in _orchs(fm)]
    _step(fm, done, SEASON, weather=weather)
    out["reference"], out["saves"] = _end_values(fm), saves
    out["graph_150"] = [_walk(o) for o in _orchs(fm)]
    out["continued"], out["graph_loaded"], out["graph_continued"] = {}, {}, {}
    for day, saved in saves.items():
        loaded, start = FieldManager.from_dict(saved), day
        out["graph_loaded"][day] = [_walk(o) for o in _orchs(loaded)]
        if day == 60:  # #515 AC2: root depth at load and ten days later
            out["depth_60"] = [o.root_state.current_depth_cm for o in _orchs(loaded)]
            _step(loaded, 60, 70, weather=weather)
            out["depth_70"] = [o.root_state.current_depth_cm for o in _orchs(loaded)]
            start = 70
        _step(loaded, start, SEASON, weather=weather)
        out["continued"][day] = _end_values(loaded)
        out["graph_continued"][day] = [_walk(o) for o in _orchs(loaded)]
    return out


@pytest.mark.parametrize("save_day", SAVE_DAYS)
def test_ac1_loaded_run_is_the_uninterrupted_run(runs: dict, save_day: int) -> None:
    label = f"{runs['weather']} d={save_day}"
    _assert_identical(runs["continued"][save_day], runs["reference"], label)


# AC2(i) names d=60 and d=100; every save day costs little more and adds the
# post-flowering save under De Bilt weather (d=130).
@pytest.mark.parametrize("save_day", SAVE_DAYS)
def test_577_ac2_full_graph_identical_right_after_load(
    runs: dict, save_day: int
) -> None:
    pairs = zip(
        runs["graph_loaded"][save_day], runs["graph_saved"][save_day], strict=True
    )
    for i, (got, want) in enumerate(pairs):
        assert any(".cumulative_evap_mm" in k for k in want)  # private memory
        assert any("._stress_history[" in k for k in want)  # deque items
        diff = _mismatches(got, want)
        assert diff == [], f"{runs['weather']} d={save_day} patch {i}: {diff[:10]}"


@pytest.mark.parametrize("save_day", SAVE_DAYS)
def test_577_ac2_full_graph_identical_at_day_150(runs: dict, save_day: int) -> None:
    pairs = zip(runs["graph_continued"][save_day], runs["graph_150"], strict=True)
    for i, (got, want) in enumerate(pairs):
        diff = _mismatches(got, want)
        assert diff == [], f"{runs['weather']} d={save_day} patch {i}: {diff[:10]}"


def test_ac2_root_depth_keeps_growing_after_load(runs: dict) -> None:
    """Rebinding ``orch.root_state`` froze the reported depth at the saved value."""
    for i, (at_60, at_70) in enumerate(
        zip(runs["depth_60"], runs["depth_70"], strict=True)
    ):
        assert at_70 > at_60, f"patch {i}: root depth {at_60} -> {at_70} cm"


def test_ac3_ac4_plant_n_and_grain_fill_restored_exactly(runs: dict) -> None:
    """Shoot N reloaded as 0, and grain-fill progress was not saved at all."""
    for day in GUARD_DAYS:
        for i, orch in enumerate(_orchs(FieldManager.from_dict(runs["saves"][day]))):
            want = runs["originals"][day][i]
            assert want["plant_n_state.n_stock_kg_ha"] > 0.0
            prefixes = ("plant_n_state.", "canopy.state.grain_fill", "canopy.state.lag")
            want = {k: v for k, v in want.items() if k.startswith(prefixes)}
            got = {k: v for k, v in _state_view(orch).items() if k in want}
            assert _mismatches(got, want) == []
    if runs["weather"] == "legacy":  # under De Bilt grain fill starts after d=100
        assert runs["originals"][100][1]["canopy.state.grain_fill_start_gdd"] > 0.0


@pytest.mark.parametrize("save_day", GUARD_DAYS)
def test_ac8_every_state_container_round_trips(runs: dict, save_day: int) -> None:
    """Every public attribute of every soil and plant state container survives a load.

    Containers are discovered from the orchestrator, so a new ``*State`` that
    is neither saved nor listed in ``_COMPARED`` fails here instead of
    dropping out of saves silently, as sulfur did. Every state object a
    subscribed runtime holds must also be the orchestrator's own object: the
    root-state bug was runtimes advancing a copy the load had orphaned.
    """
    for i, orch in enumerate(_orchs(FieldManager.from_dict(runs["saves"][save_day]))):
        discovered = _discover_states(orch)
        assert set(discovered.values()) == _COMPARED, "state container not saved"
        for holder, state in _runtime_held_states(orch):
            assert id(state) in discovered, f"patch {i}: {holder} is orphaned"
        mismatches = _mismatches(_state_view(orch), runs["originals"][save_day][i])
        assert mismatches == [], f"d={save_day} patch {i}: {mismatches[:10]}"


def test_ac9_save_without_new_keys_loads_and_steps(runs: dict) -> None:
    """A pre-#515 save, without #577's ``runtime_memory`` either, still loads."""
    assert SCHEMA_VERSION == 1
    legacy = copy.deepcopy(runs["saves"][60])
    for pdata in legacy["fields"]["f1"]["patches"]:
        for key in ("plant_n_state", "management_plan", "day_counter"):
            del pdata[key]
        del pdata["harvested_grain_g_m2"], pdata["harvested_crop_key"]
        del pdata["runtime_memory"], pdata["potential_canopy_state"]  # #660
        for key in (
            "grain_fill_start_gdd",
            "lag_start_biomass_g_m2",
            "grain_number_frozen",
        ):
            del pdata["canopy_state"][key]
        for key in ("s_available", "s_adsorbed", "s_organic"):
            del pdata["soil_snapshot"][key]
        assert set(pdata) == {
            "config",
            "soil_snapshot",
            "canopy_state",
            "phenology_state",
            "root_state",
        }
    loaded = FieldManager.from_dict(legacy)
    for orch in _orchs(loaded):  # memory starts fresh, as before #577
        assert _runtime(orch, ETRuntime)._evap_state.cumulative_evap_mm == 0.0
        assert not _runtime(orch, CanopyRuntime)._stress_history
    _step(loaded, 60, 70, weather=runs["weather"])
    for orch in _orchs(loaded):
        assert orch.day_counter == 10  # pre-#515 behaviour: the counter restarts
        assert math.isfinite(orch.canopy.state.biomass_g_m2)
        assert orch.canopy.state.biomass_g_m2 > 0.0


def _mutate_unexercised_memory(orch: Orch) -> None:
    """Set memory the default scenario leaves at its initial value (#577 AC3)."""
    frozen = _runtime(orch, AggregationRuntime)._was_frozen
    frozen[:] = [i % 2 == 0 for i in range(len(frozen))]
    canopy = _runtime(orch, CanopyRuntime)
    canopy._consecutive_wilt_days, canopy._consecutive_waterlog_days = 2, 1
    residue = _runtime(orch, ETRuntime)._residue
    residue.cover_fraction, residue.decay_half_life_days = 0.4, 30.0
    disruption = orch.som._disruption_days
    disruption[:] = [(3, 0, 5)[i % 3] for i in range(len(disruption))]


def test_577_ac3_memory_the_default_scenario_does_not_exercise() -> None:
    fm = _new_manager()
    for orch in _orchs(fm):
        orch.p_cycle.apply_slow_release_p(0, 20.0, 90)
    _step(fm, 0, 60)
    for orch in _orchs(fm):
        _mutate_unexercised_memory(orch)
        assert orch.p_cycle._slow_release_schedules[0]  # P still pending at d=60
    loaded = FieldManager.from_dict(_save(fm))
    for i, (got, want) in enumerate(zip(_orchs(loaded), _orchs(fm), strict=True)):
        assert _mismatches(_walk(got), _walk(want)) == [], f"load, patch {i}"
    _step(fm, 60, SEASON)
    _step(loaded, 60, SEASON)
    for i, (got, want) in enumerate(zip(_orchs(loaded), _orchs(fm), strict=True)):
        assert _mismatches(_walk(got), _walk(want)) == [], f"day 150, patch {i}"


def _pending_s(orch: Orch) -> float:
    schedules = orch.s_cycle._slow_release_schedules
    return sum(s.remaining_amount_kg_ha for layer in schedules for s in layer)


def test_577_ac4_unreleased_elemental_s_survives_a_load() -> None:
    fm = _new_manager()
    fm.fields["f1"].apply_fertilizer("elemental_s", 40.0)
    _step(fm, 0, 20)
    loaded = FieldManager.from_dict(_save(fm))
    print(f"pending elemental S at d=20, patch 0: {_pending_s(_orchs(fm)[0]):.2f}")
    for got, want in zip(_orchs(loaded), _orchs(fm), strict=True):
        assert _pending_s(want) > 0.0
        assert _pending_s(got) == _pending_s(want)
    _step(fm, 20, 80)
    _step(loaded, 20, 80)
    for got, want in zip(_orchs(loaded), _orchs(fm), strict=True):
        for pool in ("available_s", "adsorbed_s", "organic_s"):
            assert getattr(got.s_state, pool) == getattr(want.s_state, pool), pool


def test_577_ac5_memory_payload_present_and_aliases_kept(runs: dict) -> None:
    """Every save carries the memory; restore writes into aliased lists."""
    for saved in runs["saves"].values():
        for pdata in saved["fields"]["f1"]["patches"]:
            assert pdata["runtime_memory"]["ETRuntime"]["_evap_state"]
    for orch in _orchs(FieldManager.from_dict(runs["saves"][60])):
        cycle = orch.micro_cycle
        assert cycle._ph_by_layer is cycle._env.ph_by_layer


def test_577_ac7_fallow_patch_continues_exactly() -> None:
    fm = _new_manager((("sandy_temperate", "maize", 0.5), ("loam_temperate", "", 0.5)))
    _step(fm, 0, 60)
    loaded = FieldManager.from_dict(_save(fm))
    assert [o.is_fallow for o in _orchs(loaded)] == [False, True]
    _step(fm, 60, SEASON)
    _step(loaded, 60, SEASON)
    assert _end_values(loaded) == _end_values(fm)
    for i, (got, want) in enumerate(zip(_orchs(loaded), _orchs(fm), strict=True)):
        assert _mismatches(_walk(got), _walk(want)) == [], f"patch {i}"


def test_ac5_sulfur_pools_round_trip_after_gypsum() -> None:
    fm = _new_manager()
    fm.fields["f1"].apply_fertilizer("gypsum", 40.0)
    _step(fm, 0, 60)
    loaded = _orchs(FieldManager.from_dict(_save(fm)))
    for orch, back, fresh in zip(
        _orchs(fm), loaded, _orchs(_new_manager()), strict=True
    ):
        for pool in ("available_s", "adsorbed_s", "organic_s"):
            assert getattr(back.s_state, pool) == getattr(orch.s_state, pool)
        assert orch.s_state.available_s != fresh.s_state.available_s


def test_ac6_plan_event_fires_once_on_day_80_after_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fm = _new_manager()
    event = ManagementEvent(day=80, action="irrigate", params={"amount_mm": 10.0})
    plan = ManagementPlan(events=[event])
    for orch in _orchs(fm):
        orch.management_plan = plan  # as the /plan route shares one plan per field
    _step(fm, 0, 60)
    loaded = FieldManager.from_dict(_save(fm))
    fired: list[list[int]] = []
    for orch in _orchs(loaded):
        assert (orch.day_counter, orch.management_plan) == (60, plan)
        log: list[int] = []
        fired.append(log)

        def record(mm: float, o: Orch = orch, log: list[int] = log) -> None:
            log.append(o.day_counter)  # the plan runs before the counter advances
            Orch.apply_irrigation(o, mm)

        monkeypatch.setattr(orch, "apply_irrigation", record)
    _step(loaded, 60, 90)
    assert fired == [[80], [80], [80]]


def test_ac7_harvested_grain_and_crop_key_round_trip() -> None:
    fm = _new_manager()
    first = fm.fields["f1"].patches[0]
    first.harvested_grain_g_m2, first.harvested_crop_key = 812.5, "maize"
    restored = FieldManager.from_dict(_save(fm)).fields["f1"].patches
    assert (restored[0].harvested_grain_g_m2, restored[0].harvested_crop_key) == (
        812.5,
        "maize",
    )
    assert (restored[1].harvested_grain_g_m2, restored[1].harvested_crop_key) == (
        None,
        None,
    )


def test_ac11_two_seasons_with_mid_season_and_boundary_saves(runs: dict) -> None:
    """Two seasons, crossing the boundary as ``routes._reset_all_crops`` does.

    Season 1 loads at d=60 (as in AC1). The field is then also saved at the
    boundary itself (after harvest, before ``reset_crop``), where a pre-#515
    load reset the sulfur pools and dropped the management plan. Season 2
    saves again at d=60. Every comparison is exact (#577 AC7).
    """
    weather = runs["weather"]
    fm = FieldManager.from_dict(runs["saves"][60])
    _step(fm, 60, SEASON, weather=weather)
    assert _end_values(fm) == runs["continued"][60]  # loading is deterministic
    _assert_identical(_end_values(fm), runs["reference"], f"{weather} season 1")
    fm.harvest_field("f1")
    resumed = FieldManager.from_dict(_save(fm))
    for i, (got, want) in enumerate(zip(_orchs(resumed), _orchs(fm), strict=True)):
        assert _mismatches(_state_view(got), _state_view(want)) == [], f"patch {i}"
    preset = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", _CLIMATE
    )
    for patch in [*fm.fields["f1"].patches, *resumed.fields["f1"].patches]:
        patch.reset_crop(preset)
    _step(fm, 0, 60, seed=43, year=2025, weather=weather)
    loaded = FieldManager.from_dict(_save(fm))
    for manager, start in ((fm, 60), (loaded, 60), (resumed, 0)):
        _step(manager, start, SEASON, seed=43, year=2025, weather=weather)
    _assert_identical(_end_values(loaded), _end_values(fm), "season 2, d=60 save")
    _assert_identical(_end_values(resumed), _end_values(fm), "season 2, boundary")


@pytest.mark.parametrize("bad", [-1, 1.5, True, "60"])
def test_day_counter_rejects_invalid_values(bad: Any) -> None:
    orch = _orchs(_new_manager())[0]
    with pytest.raises(ValueError, match="day_counter"):
        orch.day_counter = bad
