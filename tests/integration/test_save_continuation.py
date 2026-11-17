"""A mid-season load continues the same crop (#515, child A1 of #471).

Default scenario (issue #515): one field of three maize patches under
``netherlands_temperate`` (sandy/loam/clay at 0.333/0.334/0.333), seed-42
weather from 2024-04-01, urea 60 kg N/ha before day 1. A *save at day d* is
``FieldManager.to_dict()`` after d steps, a JSON round trip, then
``FieldManager.from_dict()``. The AC1 bounds are the measured residual of the
per-day runtime caches a load does not carry (listed in the AC8 guard), so
they are model-derived and cite no literature.
"""

from __future__ import annotations

import copy
import json
import math
from datetime import date
from enum import Enum
from functools import cache
from operator import attrgetter
from pathlib import Path
from typing import Any

import pytest

from agrogame.game.field import FieldManager, PatchConfig
from agrogame.game.save import SCHEMA_VERSION
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.sim.orchestrator import FullSimulationOrchestrator as Orch
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

_CLIMATE = "netherlands_temperate"
_SOILS = {"sandy_temperate": 0.333, "loam_temperate": 0.334, "clay_temperate": 0.333}
SAVE_DAYS = (30, 60, 100, 130)
GUARD_DAYS = (60, 100)
SEASON = 150
# AC1: relative bounds, plus 1.0 kg N/ha absolute on profile NO3.
_REL_BOUNDS = {"grain": 0.02, "agb": 0.02, "shoot_n": 0.05, "root": 0.005, "som": 0.001}
# AC8: every *State container reachable from the orchestrator. A new soil
# module (potassium #502, soil temperature #462, salinity #468) must be saved
# and added here, or the discovery assertion in the AC8 test fails.
_COMPARED = frozenset(
    "water_state n_state p_state s_state chem_state redox_state micro_state "
    "agg_state pore_state biopore_state gas_state microbes.state canopy.state "
    "phenology.state root_state plant_n_state".split()
)


@cache
def _weather(seed: int, year: int) -> tuple[Any, ...]:
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[_CLIMATE]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    return tuple(gen.generate(SEASON, date(year, 4, 1)).records)


def _new_manager() -> FieldManager:
    fm = FieldManager()
    configs = [PatchConfig(s, "maize", _CLIMATE, a) for s, a in _SOILS.items()]
    fm.add_field("f1", configs).apply_fertilizer("urea", 60.0)
    return fm


def _step(
    fm: FieldManager, start: int, end: int, seed: int = 42, year: int = 2024
) -> None:
    for rec in _weather(seed, year)[start:end]:
        fm.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )


def _save(fm: FieldManager) -> dict[str, Any]:
    saved: dict[str, Any] = json.loads(json.dumps(fm.to_dict()))
    return saved


def _orchs(fm: FieldManager) -> list[Orch]:
    return [p.orch for p in fm.fields["f1"].patches]


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
            "shoot_n": o.plant_n_stock_kg_ha,
            "root": o.root_state.current_depth_cm,
            "som": sum(_som_pools(o)[0::2]),
            "no3": sum(o.n_state.no3),
        }
        for o in _orchs(fm)
    ]


def _assert_within_ac1(loaded: list[dict], ref: list[dict], label: str) -> None:
    for i, (got, want) in enumerate(zip(loaded, ref, strict=True)):
        rel = {k: f"{100 * (got[k] - want[k]) / want[k]:+.3f}%" for k in _REL_BOUNDS}
        print(f"{label} patch {i}: {rel} no3 {got['no3'] - want['no3']:+.3f} kg/ha")
        for key, bound in _REL_BOUNDS.items():
            assert got[key] == pytest.approx(want[key], rel=bound), (label, i, key)
        assert got["no3"] == pytest.approx(want["no3"], abs=1.0), (label, i, "no3")


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


def _mismatches(got: dict[str, Any], want: dict[str, Any]) -> list[str]:
    def same(a: Any, b: Any) -> bool:
        if isinstance(b, float) and isinstance(a, int | float):
            return math.isclose(a, b, rel_tol=0.0, abs_tol=1e-9)
        return bool(a == b)

    keys = sorted(got.keys() | want.keys())
    return [
        f"{k}: {got.get(k)!r} != {want.get(k)!r}"
        for k in keys
        if not same(got.get(k), want.get(k))
    ]


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
    handlers = [h for hs in orch.event_bus._handlers.values() for h in hs]
    owners = {id(h.__self__): h.__self__ for h in handlers if hasattr(h, "__self__")}
    return [
        (f"{type(owner).__name__}.{attr}", value)
        for owner in owners.values()
        for attr, value in vars(owner).items()
        if not attr.startswith("_") and type(value).__name__.endswith("State")
    ]


@pytest.fixture(scope="module")
def runs() -> dict[str, Any]:
    """One uninterrupted default-scenario run, its saves and their continuations."""
    fm, saves, originals, done = _new_manager(), {}, {}, 0
    for day in SAVE_DAYS:
        _step(fm, done, day)
        done, saves[day] = day, _save(fm)
        if day in GUARD_DAYS:
            originals[day] = [_state_view(o) for o in _orchs(fm)]
    _step(fm, done, SEASON)
    out: dict[str, Any] = {"reference": _end_values(fm), "saves": saves}
    out["originals"], out["continued"] = originals, {}
    for day, saved in saves.items():
        loaded, start = FieldManager.from_dict(saved), day
        if day == 60:  # AC2: root depth at load and ten days later
            out["depth_60"] = [o.root_state.current_depth_cm for o in _orchs(loaded)]
            _step(loaded, 60, 70)
            out["depth_70"] = [o.root_state.current_depth_cm for o in _orchs(loaded)]
            start = 70
        _step(loaded, start, SEASON)
        out["continued"][day] = _end_values(loaded)
    return out


@pytest.mark.parametrize("save_day", SAVE_DAYS)
def test_ac1_loaded_run_tracks_uninterrupted_run(runs: dict, save_day: int) -> None:
    _assert_within_ac1(runs["continued"][save_day], runs["reference"], f"d={save_day}")


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
    assert runs["originals"][100][1]["canopy.state.grain_fill_start_gdd"] > 0.0


@pytest.mark.parametrize("save_day", GUARD_DAYS)
def test_ac8_every_state_container_round_trips(runs: dict, save_day: int) -> None:
    """Every public attribute of every soil and plant state container survives a load.

    Containers are discovered from the orchestrator, so a new ``*State`` that
    is neither saved nor listed in ``_COMPARED`` fails here instead of
    dropping out of saves silently, as sulfur did. Every state object a
    subscribed runtime holds must also be the orchestrator's own object: the
    root-state bug was runtimes advancing a copy the load had orphaned.

    Excluded on purpose: per-day runtime caches that refill from restored
    state within a day or two. Their loss is the AC1 residual (#471):

    - root-fraction smoothing: ``SOMRuntime._root_fracs_smoothed`` and
      ``MicrobesRuntime._root_fractions_smoothed`` re-seed from ``root_state``;
    - Birch-effect wet/dry memory: ``_prev_wfps`` on ``SOMRuntime`` and
      ``AggregationRuntime`` restart at WFPS 0.5, and the countdown
      ``ThreePoolSOM._disruption_days`` restarts at 0;
    - ET stage-2 evaporation: ``ETRuntime._evap_state`` (cumulative
      evaporation since wetting) and ``ETRuntime._residue``;
    - the CO2 buffer ``FullSimulationOrchestrator._co2_buffer``, yesterday's
      respiration for gas diffusion;
    - environmental caches: ``EnvironmentalCache`` (``_env``) in the N, P, S
      and micronutrient cycles, ``NitrogenRuntime._eh_by_layer``, the
      ``CanopyRuntime`` stress memory, waterlog/wilt counters and root-depth
      cache, and the orchestrator's ``_last_biomass_inc_g_m2`` and
      ``_pending_root_canopy_inc_g_m2``;
    - the ``cumulative_co2_c_kg_ha`` SOM diagnostic (only pool C and N are
      compared).
    """
    for i, orch in enumerate(_orchs(FieldManager.from_dict(runs["saves"][save_day]))):
        discovered = _discover_states(orch)
        assert set(discovered.values()) == _COMPARED, "state container not saved"
        for holder, state in _runtime_held_states(orch):
            assert id(state) in discovered, f"patch {i}: {holder} is orphaned"
        mismatches = _mismatches(_state_view(orch), runs["originals"][save_day][i])
        assert mismatches == [], f"d={save_day} patch {i}: {mismatches[:10]}"


def test_ac9_save_without_new_keys_loads_and_steps(runs: dict) -> None:
    assert SCHEMA_VERSION == 1
    legacy = copy.deepcopy(runs["saves"][60])
    for pdata in legacy["fields"]["f1"]["patches"]:
        for key in ("plant_n_state", "management_plan", "day_counter"):
            del pdata[key]
        del pdata["harvested_grain_g_m2"], pdata["harvested_crop_key"]
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
    _step(loaded, 60, 70)
    for orch in _orchs(loaded):
        assert orch.day_counter == 10  # pre-#515 behaviour: the counter restarts
        assert math.isfinite(orch.canopy.state.biomass_g_m2)
        assert orch.canopy.state.biomass_g_m2 > 0.0


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
    saves again at d=60.
    """
    fm = FieldManager.from_dict(runs["saves"][60])
    _step(fm, 60, SEASON)
    assert _end_values(fm) == runs["continued"][60]  # loading is deterministic
    _assert_within_ac1(_end_values(fm), runs["reference"], "season 1")
    fm.harvest_field("f1")
    resumed = FieldManager.from_dict(_save(fm))
    for i, (got, want) in enumerate(zip(_orchs(resumed), _orchs(fm), strict=True)):
        assert _mismatches(_state_view(got), _state_view(want)) == [], f"patch {i}"
    preset = load_crop_presets(Path("data/crops/presets.yaml")).get_preset(
        "maize", _CLIMATE
    )
    for patch in [*fm.fields["f1"].patches, *resumed.fields["f1"].patches]:
        patch.reset_crop(preset)
    _step(fm, 0, 60, seed=43, year=2025)
    mid_season = _save(fm)
    loaded = FieldManager.from_dict(mid_season)
    for manager, start in ((fm, 60), (loaded, 60), (resumed, 0)):
        _step(manager, start, SEASON, seed=43, year=2025)
    _assert_within_ac1(_end_values(loaded), _end_values(fm), "season 2, d=60 save")
    _assert_within_ac1(_end_values(resumed), _end_values(fm), "season 2, boundary save")


@pytest.mark.parametrize("bad", [-1, 1.5, True, "60"])
def test_day_counter_rejects_invalid_values(bad: Any) -> None:
    orch = _orchs(_new_manager())[0]
    with pytest.raises(ValueError, match="day_counter"):
        orch.day_counter = bad
