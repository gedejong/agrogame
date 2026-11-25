"""The potential-production shadow canopy behind ``growth_vs_potential`` (#660).

``CanopyRuntime`` steps a bus-less copy of the crop's canopy with water and
nutrients unlimited and no damage (van Ittersum & Rabbinge 1997). It must
leave the simulation untouched, bound the actual canopy from above, follow its
stage, survive a save and load, and start afresh on every replant.

Scenario: unmanaged Sahel maize on loam (the #660 drought case, so actual and
potential diverge), two seasons of 100 days from 2024-04-01, replanted on day
100. Maize matures on day 77 at seed 42, so each season reaches maturity.
"""

from __future__ import annotations

import copy
import json
from dataclasses import fields
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from agrogame.game.field import FieldManager, Patch, PatchConfig
from agrogame.params.phenology import PhenologyStage
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.orchestrator import FullSimulationOrchestrator as Orch
from agrogame.soil.canopy.events import FrostDamageApplied, Harvested
from agrogame.soil.canopy.runtime import CanopyRuntime
from agrogame.soil.phenology import GddAccumulated, StageChanged
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

CLIMATE = "sahel_arid"
SEASON = 100
SEEDS = (42, 43)


@cache
def _weather(seed: int) -> tuple[WeatherRecord, ...]:
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[CLIMATE]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    return tuple(gen.generate(2 * SEASON, date(2024, 4, 1)).records)


def _manager() -> FieldManager:
    fm = FieldManager()
    fm.add_field("f1", [PatchConfig("loam_temperate", "maize", CLIMATE, 1.0)])
    return fm


def _patch(fm: FieldManager) -> Patch:
    return fm.fields["f1"].patches[0]


def _step(fm: FieldManager, rec: WeatherRecord) -> None:
    fm.step_day(
        drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
        tmin_c=rec.tmin_c,
        tmax_c=rec.tmax_c,
        shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
        sim_date=rec.day,
    )


def _replant(patch: Patch) -> None:
    patch.harvest()
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    patch.reset_crop(crops.get_preset("maize", CLIMATE))


def _canopy_runtime(orch: Orch) -> CanopyRuntime:
    return next(rt for rt in orch._runtimes if isinstance(rt, CanopyRuntime))


def _disable_shadow(orch: Orch) -> None:
    """Unhook the shadow entirely: no relays, no daily step."""
    rt = _canopy_runtime(orch)
    orch.event_bus.unsubscribe(StageChanged, rt._on_potential_stage)
    orch.event_bus.unsubscribe(GddAccumulated, rt._on_potential_gdd)
    orch.event_bus.unsubscribe(Harvested, rt._on_potential_harvest)
    skip = rt._potential
    skip.daily_step = lambda **_: None  # type: ignore[method-assign,assignment]


def _run(seed: int, days: range, fm: FieldManager, shadow: bool = True) -> list[Any]:
    """Step ``days`` (replanting on day SEASON); return each day's full save."""
    out = []
    if not shadow:
        _disable_shadow(_patch(fm).orch)
    for day in days:
        if day == SEASON:
            _replant(_patch(fm))
            if not shadow:
                _disable_shadow(_patch(fm).orch)
        _step(fm, _weather(seed)[day])
        out.append(_patch(fm).to_dict())
    return out


@pytest.mark.parametrize("seed", SEEDS)
def test_shadow_is_read_only_over_two_seasons(seed: int) -> None:
    """B2: with the shadow unhooked, every saved quantity is bit-identical."""
    with_shadow = _run(seed, range(2 * SEASON), _manager())
    without = _run(seed, range(2 * SEASON), _manager(), shadow=False)
    for day, (a, b) in enumerate(zip(with_shadow, without, strict=True)):
        a.pop("potential_canopy_state")
        b.pop("potential_canopy_state")
        assert a == b, f"day {day}"


@pytest.mark.parametrize("seed", SEEDS)
def test_potential_bounds_actual_and_follows_its_stage(seed: int) -> None:
    fm = _manager()
    ratios: dict[int, float] = {}
    for day in range(2 * SEASON):
        if day == SEASON:
            old = _patch(fm).orch.potential_canopy
            _replant(_patch(fm))
            fresh = _patch(fm).orch.potential_canopy
            assert fresh is not None and fresh is not old, "replant: a new shadow"
            assert (fresh.state.lai, fresh.state.biomass_g_m2) == (0.0, 0.0)
        _step(fm, _weather(seed)[day])
        orch = _patch(fm).orch
        pot = orch.potential_canopy
        assert pot is not None and pot.event_bus is None
        assert pot._current_stage == orch.canopy._current_stage, f"day {day}"
        assert pot.state.grain_fill_start_gdd == orch.canopy.state.grain_fill_start_gdd
        assert orch.canopy.state.biomass_g_m2 <= pot.state.biomass_g_m2, f"day {day}"
        if pot.state.biomass_g_m2 > 0.0:
            ratios[day] = orch.canopy.state.biomass_g_m2 / pot.state.biomass_g_m2
    # Season 1 is a drought (#660 B8): far below potential by day 45. Season 2,
    # sown into the rains, starts again from its own potential: a shadow that
    # carried season 1's biomass would read far below 0.9.
    assert ratios[44] < 0.40
    assert ratios[SEASON + 20] > 0.90
    # Maturity freezes both canopies, so the ratio freezes too.
    assert _patch(fm).orch.phenology.state.stage == PhenologyStage.MATURITY
    assert ratios[2 * SEASON - 1] == ratios[2 * SEASON - 2]


def _save(fm: FieldManager) -> dict[str, Any]:
    saved: dict[str, Any] = json.loads(json.dumps(fm.to_dict()))
    return saved


@pytest.mark.parametrize("save_day", (60, SEASON + 30))
def test_save_and_load_continue_the_shadow_exactly(save_day: int) -> None:
    """B4: a load mid-season 1 or 2 continues the potential bit-identically."""
    seed = SEEDS[0]
    reference = _run(seed, range(2 * SEASON), _manager())
    fm = _manager()
    _run(seed, range(save_day), fm)
    loaded = FieldManager.from_dict(_save(fm))
    continued = _run(seed, range(save_day, 2 * SEASON), loaded)
    pairs = zip(continued, reference[save_day:], strict=True)
    for day, (got, want) in enumerate(pairs, save_day):
        assert got["potential_canopy_state"] == want["potential_canopy_state"], day


def _ratios(fm: FieldManager) -> list[float]:
    out = []
    for patch in fm.fields["f1"].patches:
        pot = patch.orch.potential_canopy
        assert (
            pot is not None and pot._current_stage == patch.orch.canopy._current_stage
        )
        out.append(patch.orch.canopy.state.biomass_g_m2 / pot.state.biomass_g_m2)
    return out


def _load_without_potential(fm: FieldManager) -> FieldManager:
    saved = _save(fm)
    for pdata in saved["fields"]["f1"]["patches"]:
        del pdata["potential_canopy_state"]
    return FieldManager.from_dict(copy.deepcopy(saved))


def _step_after_old_load(
    fm: FieldManager, rec: WeatherRecord, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[float, float]]:
    """Step one day; return each patch's (ratio, s), s the applied factor.

    Amended B4 (refiner's ruling, #660): one day after a keyless load the
    ratio lies in [s, 1.0], s = min(canopy.state.last_water_stress, the
    nutrient minimum) applied that day. Both canopies start the day with the
    same LAI, light, temperature, VPD factor and root share, so the ratio is
    (B + s'Δ) / (B + Δ) with s' = s / VPD factor >= s. Frost debits only the
    actual canopy and waives the floor; these days have none, and say so.
    """
    patches = fm.fields["f1"].patches
    nutrient_min: dict[int, float] = {}
    frosts: list[FrostDamageApplied] = []
    for i, patch in enumerate(patches):
        canopy = patch.orch.canopy

        def _recording(
            *args: Any, _i: int = i, _orig: Any = canopy.daily_step, **kw: Any
        ) -> Any:
            nutrient_min[_i] = kw["n_stress"]
            return _orig(*args, **kw)

        monkeypatch.setattr(canopy, "daily_step", _recording)
        patch.orch.event_bus.subscribe(FrostDamageApplied, frosts.append)
    _step(fm, rec)
    assert frosts == [], "the floor is waived on a frost day"
    water = [patch.orch.canopy.state.last_water_stress for patch in patches]
    factors = [min(w, nutrient_min[i]) for i, w in enumerate(water)]
    return list(zip(_ratios(fm), factors, strict=True))


def test_old_save_seeds_the_potential_from_the_actual_canopy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B4 as amended: a save without the key reads 1.0 at the load, [s, 1] next.

    The #660 Validation Plan's game: the default NL maize scenario (three
    soils), saved mid-season on day 60. Seeded from the actual canopy, the
    ratio a day later is (B + actual growth) / (B + potential growth): the
    N-limited sandy patch reads 0.966, a true reading above its own s.
    """
    key = "netherlands_temperate"
    nl = load_climate_presets(Path("data/climate/presets.yaml")).climates[key]
    weather = SyntheticWeatherGenerator(nl, seed=42).generate(61, date(2024, 4, 1))
    fm = FieldManager()
    soils = [("sandy_temperate", 0.333), ("loam_temperate", 0.334)]
    soils.append(("clay_temperate", 0.333))
    fm.add_field("f1", [PatchConfig(s, "maize", key, a) for s, a in soils])
    for rec in weather.records[:60]:
        _step(fm, rec)
    loaded = _load_without_potential(fm)
    assert _ratios(loaded) == [1.0, 1.0, 1.0]
    for ratio, s in _step_after_old_load(loaded, weather.records[60], monkeypatch):
        assert 0.0 < s <= ratio <= 1.0, (ratio, s)


def test_old_save_under_drought_never_reads_zero_or_above_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B4 as amended on the drought: 1.0 at the load, then in [s, 1].

    One day of unstressed potential growth is large beside a collapsed crop's
    biomass (Sahel maize, day 45, seed 42: 0.93 after one day), and the
    drought's s is lower still.
    """
    fm = _manager()
    _run(SEEDS[0], range(45), fm)
    loaded = _load_without_potential(fm)
    assert _ratios(loaded) == [1.0]
    [(ratio, s)] = _step_after_old_load(loaded, _weather(SEEDS[0])[45], monkeypatch)
    assert 0.0 < s <= ratio <= 1.0, (ratio, s)


def test_old_save_shadow_shares_no_state_with_the_actual_canopy() -> None:
    """A keyless load copies the actual canopy's values; it never aliases them.

    PR #673 review: a shadow sharing the actual ``CanopyState`` would step the
    real canopy twice a day after every legacy load. Mutate either canopy and
    the other must not move; and the keyless load must then run exactly as a
    load with the key does, every saved quantity but the shadow.
    """
    fm = _manager()
    _run(SEEDS[0], range(45), fm)
    loaded = _load_without_potential(fm)
    orch = _patch(loaded).orch
    potential = orch.potential_canopy
    assert potential is not None and potential.state is not orch.canopy.state
    for one, other in ((orch.canopy, potential), (potential, orch.canopy)):
        before = other.state.to_dict()
        for f in fields(one.state):
            value = getattr(one.state, f.name)
            setattr(
                one.state,
                f.name,
                value + 7 if not isinstance(value, bool) else not value,
            )
        assert other.state.to_dict() == before

    keyed = FieldManager.from_dict(_save(fm))
    legacy = _load_without_potential(fm)
    with_key = _run(SEEDS[0], range(45, 52), keyed)
    without = _run(SEEDS[0], range(45, 52), legacy)
    for day, (a, b) in enumerate(zip(with_key, without, strict=True), 45):
        a.pop("potential_canopy_state")
        b.pop("potential_canopy_state")
        assert a == b, f"day {day}"


def test_fallow_patch_has_no_shadow_and_saves_none() -> None:
    fm = FieldManager()
    fm.add_field("f1", [PatchConfig("loam_temperate", "", CLIMATE, 1.0)])
    _step(fm, _weather(SEEDS[0])[0])
    assert _patch(fm).orch.potential_canopy is None
    saved = _save(fm)
    assert saved["fields"]["f1"]["patches"][0]["potential_canopy_state"] is None
    assert _patch(FieldManager.from_dict(saved)).orch.potential_canopy is None
