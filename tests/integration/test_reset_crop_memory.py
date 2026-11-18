"""A crop change keeps the soil's runtime memory (#583).

``reset_crop`` rebuilds every soil module. Before #583 the rebuild also wiped
the soil's cross-day memory at each crop change in an uninterrupted run:
unreleased elemental S and slow-release P, the Ritchie (1972) stage-2 clock,
the aggregation cadence, the wet-dry memory. Memory now follows the soil/crop
split declared in ``_CROP_MEMORY``: soil-owned memory carries across, and
crop-owned memory resets with the crop it mirrors.

Every comparison is exact (``==``) except the S and P ledgers, which close to
1e-6 kg/ha. The full-graph walk and its helpers come from the #577 save test
in this directory.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from test_save_continuation import (
    _CLIMATE,
    _SOILS,
    _mismatches,
    _new_manager,
    _orchs,
    _runtime,
    _save,
    _step,
    _walk,
)

from agrogame.atmosphere.et.runtime import ETRuntime
from agrogame.game.field import FieldManager
from agrogame.params.memory import RuntimeMemory, to_json_native
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator as Orch
from agrogame.soil.aggregation.runtime import AggregationRuntime
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.soil.phosphorus.cycle import PhosphorusCycle
from agrogame.soil.sulfur.cycle import SulfurCycle
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

LOAM_NL_MAIZE = ("loam_temperate", "netherlands_temperate", "maize")
SAHEL_SORGHUM = ("sandy_subsaharan", "sahel_arid", "sorghum")
_START = date(2024, 4, 15)
_DAYS = 345  # AC4: 150 crop days, 45 fallow days, 150 crop days


@cache
def _weather(climate: str) -> tuple[WeatherRecord, ...]:
    """One continuous series from 2024-04-15, seed 42, sliced by every test."""
    preset = load_climate_presets(Path("data/climate/presets.yaml")).climates[climate]
    gen = SyntheticWeatherGenerator(preset, seed=42)
    return tuple(gen.generate(_DAYS, _START).records)


def _preset(crop: str | None, climate: str) -> Any:
    if crop is None:
        return None
    return load_crop_presets(Path("data/crops/presets.yaml")).get_preset(crop, climate)


def _orch(soil: str, climate: str, crop: str | None) -> Orch:
    """A planted patch, or a bare one for ``crop=None``."""
    profile = load_soil_presets(Path("soils/presets.yaml")).soils[soil]
    latitude = (
        load_climate_presets(Path("data/climate/presets.yaml"))
        .climates[climate]
        .latitude_deg
    )
    return Orch(
        profile,
        crop=_preset(crop, climate),
        latitude_deg=latitude,
        fallow=crop is None,
    )


def _reset(orch: Orch, crop: str | None, climate: str) -> None:
    orch.reset_crop(_preset(crop, climate), fallow=crop is None)


def _run(orch: Orch, climate: str, start: int, end: int) -> None:
    for rec in _weather(climate)[start:end]:
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )


def _pending(cycle: SulfurCycle | PhosphorusCycle) -> float:
    """Unreleased slow-release fertiliser in the cycle (kg/ha)."""
    schedules = cycle._slow_release_schedules
    return sum(s.remaining_amount_kg_ha for layer in schedules for s in layer)


def _sentinels(orch: Orch) -> tuple[float, float, float, int]:
    """Stage-2 clock, pending S and P, and the aggregation cadence."""
    return (
        _runtime(orch, ETRuntime)._evap_state.cumulative_evap_mm,
        _pending(orch.s_cycle),
        _pending(orch.p_cycle),
        _runtime(orch, AggregationRuntime)._day_count,
    )


def _soil_memory(orch: Orch) -> dict[str, Any]:
    """Soil-owned memory of every holder that has any."""
    memory = orch.runtime_memory_to_dict(soil_only=True)
    return {name: data for name, data in memory.items() if data}


def _crop_part(holder: RuntimeMemory) -> dict[str, Any]:
    """A holder's crop-owned names, and those of the holders nested in it."""
    out = {n: to_json_native(getattr(holder, n)) for n in holder._CROP_MEMORY}
    for name in holder._MEMORY:
        value = getattr(holder, name)
        if isinstance(value, RuntimeMemory) and name not in holder._CROP_MEMORY:
            out[name] = _crop_part(value)
    return out


def _crop_memory(orch: Orch) -> dict[str, Any]:
    return {name: _crop_part(h) for name, h in orch._memory_holders().items()}


# (source, target) crop of each transition the game performs: Harvest, Plant,
# and the season start's crop->crop and fallow->fallow.
TRANSITIONS = {
    "crop_to_fallow": ("maize", None),
    "fallow_to_crop": (None, "maize"),
    "crop_to_crop": ("maize", "maize"),
    "fallow_to_fallow": (None, None),
}


@pytest.mark.parametrize("transition", sorted(TRANSITIONS))
def test_ac2_soil_untouched_at_the_reset_instant(transition: str) -> None:
    source, target = TRANSITIONS[transition]
    soil, climate, _crop = LOAM_NL_MAIZE
    orch = _orch(soil, climate, source)
    _run(orch, climate, 0, 30)
    orch.s_cycle.apply_elemental_s(0, 40.0)
    orch.p_cycle.apply_slow_release_p(0, 20.0, 90)
    _run(orch, climate, 30, 50)
    if source is not None:
        orch.harvest()
    # The memory is non-trivial, or equality would prove nothing. Read
    # directly, so a misclassification fails here and not only in the pin.
    sentinels = _sentinels(orch)
    clock, pending_s, pending_p, day_count = sentinels
    assert clock > 0.0 and pending_s > 0.0 and pending_p > 0.0 and day_count != 0
    print(f"{transition}: clock {clock:.2f} mm, S {pending_s:.2f}, P {pending_p:.2f}")
    memory, snapshot = _soil_memory(orch), orch.snapshot_soil().to_dict()
    _reset(orch, target, climate)
    assert _sentinels(orch) == sentinels
    assert _soil_memory(orch) == memory
    assert orch.snapshot_soil().to_dict() == snapshot
    assert _crop_memory(orch) == _crop_memory(_orch(soil, climate, target))


@pytest.mark.parametrize(
    "setting", [LOAM_NL_MAIZE, SAHEL_SORGHUM], ids=["loam_nl", "sandy_sahel"]
)
def test_ac3_a_noop_crop_change_is_invisible(setting: tuple[str, str, str]) -> None:
    """Fallow->fallow at day 140 leaves the run as a control without it."""
    soil, climate, crop = setting
    patch, control = _orch(soil, climate, crop), _orch(soil, climate, crop)
    for orch in (patch, control):
        _run(orch, climate, 0, 120)
        orch.harvest()
        _reset(orch, None, climate)
        orch.s_cycle.apply_elemental_s(0, 30.0)
        _run(orch, climate, 120, 140)
    _reset(patch, None, climate)
    for orch in (patch, control):
        _run(orch, climate, 140, 220)
    # The crop's plan clock is the only thing a crop change may restart.
    assert _mismatches(_walk(patch), _walk(control)) == ["orch._day_counter: 80 != 100"]


def _record_uptake(
    monkeypatch: pytest.MonkeyPatch, cls: type, totals: dict[str, float]
) -> None:
    """Sum ``plant_uptake_kg_ha`` of every ``daily_step`` of ``cls``."""
    original = cls.daily_step

    def daily_step(self: Any, *args: Any, **kwargs: Any) -> Any:
        flux = original(self, *args, **kwargs)
        totals[cls.__name__] += flux.plant_uptake_kg_ha
        return flux

    monkeypatch.setattr(cls, "daily_step", daily_step)


def test_ac4_s_and_p_conserved_across_harvest_fallow_sowing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    soil, climate, crop = LOAM_NL_MAIZE
    uptake: dict[str, float] = defaultdict(float)
    leached: dict[str, float] = defaultdict(float)
    applied = {"S": 0.0, "P": 0.0}
    for cls in (SulfurCycle, PhosphorusCycle):
        _record_uptake(monkeypatch, cls, uptake)

    def on_leached(ev: NutrientLeached) -> None:
        leached[ev.nutrient] += ev.amount_kg_ha

    orch = _orch(soil, climate, crop)
    orch.event_bus.subscribe(NutrientLeached, on_leached)
    s0, p0 = orch.s_cycle._total_s(), orch.p_cycle._total_p()
    orch.apply_fertilizer("urea", 60.0)

    def reset(target: str | None) -> tuple[float, float]:
        before = (_pending(orch.s_cycle), _pending(orch.p_cycle))
        _reset(orch, target, climate)
        orch.event_bus.subscribe(NutrientLeached, on_leached)  # the bus was cleared
        assert (_pending(orch.s_cycle), _pending(orch.p_cycle)) == before
        return before

    worst = {"S": 0.0, "P": 0.0}
    for day in range(_DAYS):
        if day == 100:
            orch.apply_fertilizer("elemental_s", 40.0)
            orch.p_cycle.apply_slow_release_p(0, 20.0, 90)
            applied["S"] += 40.0
            applied["P"] += 20.0
        elif day == 150:
            orch.harvest()
            pending_s, pending_p = reset(None)
            assert pending_s > 0.0 and pending_p > 0.0
        elif day == 160:  # fallow day 10: S ahead of the next crop
            orch.apply_fertilizer("elemental_s", 30.0)
            applied["S"] += 30.0
        elif day == 195:  # sowing after 45 fallow days
            pending_s, _pending_p = reset(crop)
            assert pending_s > 0.0
        _run(orch, climate, day, day + 1)
        out_s = uptake["SulfurCycle"] + leached["SO4"] - applied["S"]
        out_p = uptake["PhosphorusCycle"] + leached["P"] - applied["P"]
        residual = {
            "S": orch.s_cycle._total_s() - s0 + out_s,
            "P": orch.p_cycle._total_p() - p0 + out_p,
        }
        for nutrient, value in residual.items():
            assert abs(value) <= 1e-6, f"{nutrient} ledger off by {value} on day {day}"
            worst[nutrient] = max(worst[nutrient], abs(value))
    print(f"worst ledger residual (kg/ha): S {worst['S']:.1e}, P {worst['P']:.1e}")


def _field_memory(fm: FieldManager) -> list[tuple[float, float]]:
    """Each patch's pending elemental S and Ritchie stage-2 clock."""
    return [
        (_pending(o.s_cycle), _runtime(o, ETRuntime)._evap_state.cumulative_evap_mm)
        for o in _orchs(fm)
    ]


def test_ac5_harvest_and_plant_through_the_api_keep_s_and_the_clock() -> None:
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app
    from agrogame.api.state import games

    client = TestClient(create_app())
    patches = [
        {
            "soil_profile_key": s,
            "crop_key": c,
            "climate_key": _CLIMATE,
            "area_fraction": a,
        }
        for s, c, a in _SOILS
    ]
    fields = [{"field_id": "f1", "patches": patches}]
    gid = client.post("/api/v1/games", json={"fields": fields}).json()["game_id"]
    url = f"/api/v1/games/{gid}"
    event = {
        "day": 20,
        "action": "fertilize",
        "params": {"type": "elemental_s", "amount_kg_ha": 40.0},
    }
    plan = client.post(f"{url}/plan", json={"field_id": "f1", "events": [event]})
    assert plan.status_code == 200, plan.text
    assert client.post(f"{url}/step?days=40").status_code == 200
    fm = games[gid].field_manager
    before = _field_memory(fm)
    print(f"pending S and clock (mm) before the harvest: {before}")
    assert all(s > 0.0 and clock > 0.0 for s, clock in before)
    for action, params in (("harvest", {}), ("plant", {"crop_key": "maize"})):
        body = {"field_id": "f1", "action": action, "params": params}
        resp = client.post(f"{url}/action", json=body)
        assert resp.json()["status"] == "executed", resp.text
        assert _field_memory(fm) == before, action
    assert [o.is_fallow for o in _orchs(fm)] == [False] * 3


def test_ac5_save_right_after_a_harvest_reset_continues_exactly() -> None:
    fm = _new_manager()
    fm.fields["f1"].apply_fertilizer("elemental_s", 40.0)
    _step(fm, 0, 20)
    for patch in fm.fields["f1"].patches:
        patch.harvest()
        patch.reset_crop(None)
    assert all(o.is_fallow and _pending(o.s_cycle) > 0.0 for o in _orchs(fm))
    loaded = FieldManager.from_dict(_save(fm))
    _step(fm, 20, 50)
    _step(loaded, 20, 50)
    for i, (got, want) in enumerate(zip(_orchs(loaded), _orchs(fm), strict=True)):
        assert _mismatches(_walk(got), _walk(want)) == [], f"patch {i}"
