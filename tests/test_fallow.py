"""A bare fallow patch runs no plant (#542).

Scenario S (issue #542): one ``loam_temperate`` maize patch under
``netherlands_temperate``, urea 60 kg N/ha before day 1, seed-42 weather from
2024-04-01 stepped as ``tests/integration/test_save_continuation.py::_step``
does, 150 days of crop, then ``patch.harvest(); patch.reset_crop(None)``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from agrogame.events.recorder import RecordedEvent
from agrogame.game.field import FieldManager, Patch, PatchConfig
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.phenology.types import PhenologyStage
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets

CLIMATE = "netherlands_temperate"
SOIL = "loam_temperate"
# Scenario S, 215 fallow days, 150 days of crop 2 and 30 more fallow days (AC5).
DAYS = 150 + 215 + 150 + 30
PLANT_EVENTS = frozenset(
    "StageChanged GddAccumulated RootDepthChanged RootDistributionUpdated "
    "RootBiomassUpdated RootTurnoverOccurred BiomassAccumulated LAIUpdated "
    "LightIntercepted".split()
)
# AC7 addition: plant stress, i.e. every event the client draws as a crop icon
# from a damage or stress value (stress_icons.gd, farm_view.gd).
PLANT_STRESS_EVENTS = frozenset(
    "FrostDamageApplied HeatDamageApplied WaterStressComputed "
    "NutrientStressComputed".split()
)
Day = Sequence[RecordedEvent]


@cache
def _weather() -> tuple[Any, ...]:
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[CLIMATE]
    gen = SyntheticWeatherGenerator(climate, seed=42)
    return tuple(gen.generate(DAYS, date(2024, 4, 1)).records)


def _step(patches: Sequence[Patch], start: int, end: int) -> list[list[Day]]:
    """Step every patch over weather days ``[start, end)``; events per day."""
    out: list[list[Day]] = [[] for _ in patches]
    for rec in _weather()[start:end]:
        for patch, days in zip(patches, out, strict=True):
            patch.recorder.clear()
            patch.step_day(
                drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
                tmin_c=rec.tmin_c,
                tmax_c=rec.tmax_c,
                shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
                sim_date=rec.day,
            )
            days.append(patch.recorder.events)
    return out


def _new_patch() -> Patch:
    return Patch(PatchConfig(SOIL, "maize", CLIMATE, 1.0))


def _scenario_s(patch: Patch) -> Patch:
    patch.orch.apply_fertilizer("urea", 60.0)
    _step([patch], 0, 150)
    patch.harvest()
    patch.reset_crop(None)
    return patch


def _assert_bare_state(patch: Patch) -> None:
    """AC2 (a), (b) and AC3's ``crop_key`` invariant."""
    orch = patch.orch
    assert orch.is_fallow and patch.config.crop_key == ""
    roots = orch.root_state
    assert (roots.current_depth_cm, roots.biomass_g_m2) == (0.0, 0.0)
    assert roots.layer_fractions == [0.0] * len(orch.profile.layers)
    assert (orch.canopy.state.lai, orch.canopy.state.biomass_g_m2) == (0.0, 0.0)
    assert orch.phenology.state.stage is PhenologyStage.PLANTED
    assert orch.phenology.state.accumulated_gdd == 0.0
    assert orch.plant_n_stock_kg_ha == 0.0


def _assert_bare_day(patch: Patch, day: Day) -> float:
    """AC2 and AC4 on one fallow day; returns the day's soil evaporation (mm)."""
    _assert_bare_state(patch)
    types = {e.event_type for e in day}
    assert not types & PLANT_EVENTS
    assert not types & PLANT_STRESS_EVENTS
    demands = ("plant_n_demand_kg_ha", "plant_p_demand_kg_ha", "plant_s_demand_kg_ha")
    ticks = [e.data for e in day if e.event_type == "DayTick"]
    assert ticks and all(t[k] == 0.0 for t in ticks for k in demands)
    (uptake,) = (e.data for e in day if e.event_type == "PlantNUptakeComputed")
    assert uptake["uptake_kg_ha"] == 0.0
    (et,) = (e.data for e in day if e.event_type == "EvapotranspirationComputed")
    assert et["transpiration_mm"] == 0.0
    return float(et["evaporation_mm"])


def _subscription_order(orch: FullSimulationOrchestrator) -> dict[str, list[str]]:
    """Engine handler order per event type, as ``test_orchestrator_wiring.py``
    reads it, without the patch's own ``EventRecorder``."""
    out: dict[str, list[str]] = {}
    for etype, handlers in orch.event_bus._handlers.items():
        owners = [type(h.__self__).__name__ for h in handlers]
        ids = [f"{o}.{h.__name__}" for o, h in zip(owners, handlers, strict=True)]
        ids = [i for i in ids if not i.startswith("EventRecorder.")]
        if ids:
            out[etype.__name__] = ids
    return out


def _profile() -> Any:
    return load_soil_presets(Path("soils/presets.yaml")).soils[SOIL]


def test_fallow_flag_rejects_a_crop_and_is_read_only() -> None:
    """AC1: explicit flag; a bare ``crop=None`` keeps the generic plant."""
    maize = load_crop_presets().get_preset("maize", CLIMATE)
    with pytest.raises(ValueError, match="fallow=True takes no crop preset"):
        FullSimulationOrchestrator(_profile(), crop=maize, fallow=True)
    orch = FullSimulationOrchestrator(_profile(), fallow=True)
    with pytest.raises(ValueError, match="'maize'"):
        orch.reset_crop(maize, fallow=True)
    with pytest.raises(AttributeError):
        orch.is_fallow = False  # type: ignore[misc]
    orch.reset_crop(maize)
    assert not orch.is_fallow
    orch.reset_crop(None)
    assert not orch.is_fallow
    assert orch.root_state.current_depth_cm == 5.0  # generic plant's seedling


def test_300_day_fallow_runs_no_plant() -> None:
    """AC2, AC4 and the AC7 addition: no plant event or plant stress, ever."""
    patch = _scenario_s(_new_patch())
    _assert_bare_state(patch)
    (days,) = _step([patch], 150, 450)
    evaporation = [_assert_bare_day(patch, day) for day in days]
    assert len(evaporation) == 300
    assert sum(evaporation) > 0.0


def test_two_cycles_harvest_fallow_plant_harvest_fallow() -> None:
    """AC5: harvest → 215 d fallow → maize 150 d → harvest → 30 d fallow."""
    golden = json.loads(Path("tests/fixtures/wiring_order_golden.json").read_text())
    fallow_wiring = _subscription_order(
        FullSimulationOrchestrator(_profile(), fallow=True)
    )
    patch = _scenario_s(_new_patch())
    for day in _step([patch], 150, 365)[0]:
        _assert_bare_day(patch, day)

    patch.reset_crop(load_crop_presets().get_preset("maize", CLIMATE))
    assert _subscription_order(patch.orch) == golden
    assert patch.config.crop_key == "maize" and not patch.orch.is_fallow
    patch.orch.apply_fertilizer("urea", 60.0)
    _step([patch], 365, 366)
    assert patch.orch.root_state.current_depth_cm <= 6.5  # seedling restart
    max_lai = 0.0
    for i in range(366, 515):
        _step([patch], i, i + 1)
        max_lai = max(max_lai, patch.orch.canopy.state.lai)
    assert patch.orch.root_state.current_depth_cm > 50.0
    assert max_lai > 0.0
    assert patch.orch.canopy.state.grain_biomass_g_m2 > 0.0

    patch.harvest()
    patch.reset_crop(None)
    assert _subscription_order(patch.orch) == fallow_wiring
    for day in _step([patch], 515, 545)[0]:
        _assert_bare_day(patch, day)


def test_fallow_patch_round_trips_through_a_save() -> None:
    """AC3 and AC6: saved at fallow day 100, both copies run 200 more days."""
    fm = FieldManager()
    fm.add_field("f1", [PatchConfig(SOIL, "maize", CLIMATE, 1.0)])
    patch = _scenario_s(fm.fields["f1"].patches[0])
    _step([patch], 150, 250)
    saved = json.loads(json.dumps(fm.to_dict()))
    saved_patch = saved["fields"]["f1"]["patches"][0]
    assert saved_patch["config"]["crop_key"] == ""
    assert set(saved_patch) == set(_new_patch().to_dict())  # no new save key

    loaded = FieldManager.from_dict(saved).fields["f1"].patches[0]
    _assert_bare_state(loaded)
    _, loaded_days = _step([patch, loaded], 250, 450)
    for day in loaded_days:
        _assert_bare_day(loaded, day)
    a, b = patch.orch.snapshot_soil(), loaded.orch.snapshot_soil()
    assert sum(b.n_no3) == pytest.approx(sum(a.n_no3), abs=1.0)
    pools = ("som_labile_c", "som_intermediate_c", "som_stable_c")
    som_a, som_b = (sum(sum(getattr(s, k)) for k in pools) for s in (a, b))
    assert som_b == pytest.approx(som_a, rel=1e-3)


def test_load_discards_the_phantom_plant_of_a_pre_542_save() -> None:
    """AC3: a bare patch saved with a growing default plant loads bare."""
    planted = _new_patch()
    _step([planted], 0, 100)
    assert planted.orch.root_state.current_depth_cm > 5.0
    data = planted.to_dict()
    data["config"]["crop_key"] = ""  # what a pre-#542 harvested patch saved
    loaded = FieldManager.from_dict({"fields": {"f1": {"patches": [data]}}})
    patch = loaded.fields["f1"].patches[0]
    _assert_bare_state(patch)
    assert patch.orch.snapshot_soil() == planted.orch.snapshot_soil()
