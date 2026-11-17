"""Tests for in-season pause detection and the turn manager (#470, ADR-017).

These replace the tests of the deleted ``GameTurnManager.run_season`` generator
(AGRO-110, #351, #486) with equivalent tests of :class:`PauseDetector`: frost,
N deficiency, drought, phase transitions and serialisation.
"""

from __future__ import annotations

import json
from datetime import date
from itertools import pairwise
from pathlib import Path

import pytest

from agrogame.events import BaseEvent
from agrogame.game.field import FieldManager, PatchConfig
from agrogame.game.turn import (
    DROUGHT_STAGES,
    FROST_STAGES,
    N_RESPONSE_STAGES,
    GameTurnManager,
    PatchDayObservation,
    PauseConfig,
    PauseDetector,
    PauseEvent,
    PauseLatchState,
    PauseReason,
    SeasonPhase,
    interrupt_count,
    observe_patch,
)
from agrogame.params.phenology import PhenologyStage
from agrogame.plant.events import NutrientStressComputed, WaterStressComputed
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord

DROUGHT = PauseReason.DROUGHT
NITROGEN = PauseReason.NUTRIENT_DEFICIENCY
FROST = PauseReason.FROST_WARNING
VEG = PhenologyStage.VEGETATIVE


def _obs(
    stage: PhenologyStage = VEG,
    water: float | None = 1.0,
    n: float | None = 1.0,
    crop_key: str = "maize",
    frost_threshold_c: float = 0.0,
) -> PatchDayObservation:
    return PatchDayObservation(
        crop_key=crop_key,
        stage=stage,
        water_stress=water,
        n_stress=n,
        frost_threshold_c=frost_threshold_c,
    )


def _run(
    detector: PauseDetector,
    days: list[list[PatchDayObservation]],
    start_day: int = 1,
    tmin: list[float | None] | None = None,
    field_id: str = "f1",
) -> list[PauseEvent]:
    """Feed one observation list per day; return every alert raised."""
    fired: list[PauseEvent] = []
    for offset, patches in enumerate(days):
        tomorrow = tmin[offset] if tmin is not None else None
        fired += detector.observe_field(field_id, start_day + offset, patches, tomorrow)
    return fired


# ---------------------------------------------------------------------------
# Config: defaults are exactly the refined playtest table (#470)
# ---------------------------------------------------------------------------
def test_pause_config_defaults_match_refined_table() -> None:
    cfg = PauseConfig()
    assert (cfg.drought_ks_threshold, cfg.drought_onset_days) == (0.4, 2)
    assert cfg.drought_rearm_days == 7
    assert (cfg.n_stress_threshold, cfg.n_onset_days, cfg.n_rearm_days) == (
        0.9,
        3,
        10,
    )
    assert (cfg.frost_onset_days, cfg.frost_rearm_days) == (1, 7)
    assert cfg.interrupt_spacing_days == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"drought_ks_threshold": 1.5},
        {"n_stress_threshold": -0.1},
        {"n_onset_days": 0},
        {"frost_rearm_days": -1},
        {"interrupt_spacing_days": -1},
    ],
)
def test_pause_config_rejects_invalid_values(kwargs: dict) -> None:
    with pytest.raises(ValueError):
        PauseConfig(**kwargs)


def test_stage_gates_match_the_refined_table() -> None:
    assert DROUGHT_STAGES == {
        PhenologyStage.EMERGED,
        PhenologyStage.VEGETATIVE,
        PhenologyStage.FLOWERING,
        PhenologyStage.GRAIN_FILL,
    }
    assert N_RESPONSE_STAGES == {
        PhenologyStage.EMERGED,
        PhenologyStage.VEGETATIVE,
        PhenologyStage.FLOWERING,
    }
    assert FROST_STAGES == N_RESPONSE_STAGES


# ---------------------------------------------------------------------------
# Drought: Ks onset latch and re-arm
# ---------------------------------------------------------------------------
def test_drought_fires_after_onset_days_once_per_episode() -> None:
    det = PauseDetector()
    dry = [_obs(water=0.3)]
    assert _run(det, [dry]) == []  # 1 day < onset 2
    fired = _run(det, [dry] * 20, start_day=2)
    assert [(e.day, e.reason, e.interrupt) for e in fired] == [(2, DROUGHT, True)]
    assert "0.30" in fired[0].message


def test_drought_rearms_only_after_rearm_days_clear() -> None:
    det = PauseDetector()
    dry, wet = [_obs(water=0.2)], [_obs(water=0.9)]
    first = _run(det, [dry, dry])
    assert len(first) == 1
    # 6 clear days is one short of the 7-day re-arm: the next dry spell is muted.
    assert _run(det, [wet] * 6 + [dry] * 3, start_day=3) == []
    # 7 clear days re-arm it; the next 2-day spell fires again.
    again = _run(det, [wet] * 7 + [dry] * 2, start_day=12)
    assert [e.day for e in again] == [20]


def test_drought_threshold_is_strict_and_gated_to_a_standing_crop() -> None:
    det = PauseDetector()
    assert _run(det, [[_obs(water=0.4)]] * 5) == []  # Ks == 0.4 is not < 0.4
    for stage in (PhenologyStage.PLANTED, PhenologyStage.MATURITY):
        assert _run(PauseDetector(), [[_obs(stage=stage, water=0.0)]] * 5) == []
    assert _run(PauseDetector(), [[_obs(crop_key="", water=0.0)]] * 5) == []
    assert _run(PauseDetector(), [[_obs(water=None)]] * 5) == []
    grain_fill = [_obs(stage=PhenologyStage.GRAIN_FILL, water=0.1)]
    assert len(_run(PauseDetector(), [grain_fill] * 2)) == 1


# ---------------------------------------------------------------------------
# Nitrogen: persistent stress is one alert, inside the response window only
# ---------------------------------------------------------------------------
def test_persistent_n_stress_is_one_alert() -> None:
    det = PauseDetector()
    fired = _run(det, [[_obs(n=0.6)]] * 120)
    assert [(e.day, e.reason) for e in fired] == [(3, NITROGEN)]


def test_n_alert_rearms_after_ten_clear_days() -> None:
    det = PauseDetector()
    low, ok = [_obs(n=0.8)], [_obs(n=0.95)]
    assert len(_run(det, [low] * 3)) == 1
    assert _run(det, [ok] * 9 + [low] * 5, start_day=4) == []
    assert [e.day for e in _run(det, [ok] * 10 + [low] * 3, start_day=18)] == [30]


@pytest.mark.parametrize(
    "stage",
    [PhenologyStage.PLANTED, PhenologyStage.GRAIN_FILL, PhenologyStage.MATURITY],
)
def test_no_n_alert_outside_the_response_window(stage: PhenologyStage) -> None:
    assert _run(PauseDetector(), [[_obs(stage=stage, n=0.2)]] * 30) == []


# ---------------------------------------------------------------------------
# Frost: tomorrow's tmin against the crop's own threshold, a notice only
# ---------------------------------------------------------------------------
def test_frost_notice_uses_tomorrows_tmin_and_crop_threshold() -> None:
    det = PauseDetector()
    patch = [_obs(frost_threshold_c=2.0)]
    fired = _run(det, [patch] * 3, tmin=[3.0, 1.5, 1.0])
    assert [(e.day, e.reason, e.interrupt) for e in fired] == [(2, FROST, False)]
    assert "1.5" in fired[0].message and "2.0" in fired[0].message
    # The last day of a season has no tomorrow: no frost evaluation.
    assert _run(PauseDetector(), [patch], tmin=[None]) == []


@pytest.mark.parametrize("stage", list(PhenologyStage))
def test_frost_notice_only_in_canopy_damage_stages(stage: PhenologyStage) -> None:
    fired = _run(PauseDetector(), [[_obs(stage=stage)]], tmin=[-5.0])
    assert bool(fired) == (stage in FROST_STAGES)


def test_frost_rearms_after_seven_frost_free_days() -> None:
    det = PauseDetector()
    p = [_obs()]
    tmin: list[float | None] = [-1.0] * 3 + [5.0] * 6 + [-1.0] + [5.0] * 7 + [-1.0]
    fired = _run(det, [p] * len(tmin), tmin=tmin)
    assert [e.day for e in fired] == [1, 18]


def test_frost_notice_neither_counts_nor_blocks_interrupts() -> None:
    det = PauseDetector()
    p = [_obs(water=0.1)]
    fired = _run(det, [p, p], tmin=[-3.0, 5.0])
    assert [(e.day, e.reason) for e in fired] == [(1, FROST), (2, DROUGHT)]
    assert interrupt_count(fired) == 1


# ---------------------------------------------------------------------------
# Field level: any patch, all patches watched
# ---------------------------------------------------------------------------
def test_field_condition_holds_when_any_patch_meets_it() -> None:
    det = PauseDetector()
    a_dry = [_obs(water=0.1), _obs(water=0.9), _obs(water=0.9)]
    c_dry = [_obs(water=0.9), _obs(water=0.9), _obs(water=0.2)]
    fired = _run(det, [a_dry, c_dry])
    assert [(e.day, e.field_id) for e in fired] == [(2, "f1")]
    assert "0.20" in fired[0].message


def test_fields_have_independent_latches_and_spacing() -> None:
    det = PauseDetector()
    dry = [_obs(water=0.1)]
    f1 = _run(det, [dry] * 2, field_id="f1")
    f2 = _run(det, [dry] * 2, field_id="f2")
    assert [(e.field_id, e.day) for e in f1 + f2] == [("f1", 2), ("f2", 2)]


# ---------------------------------------------------------------------------
# Global spacing: deferred, not dropped
# ---------------------------------------------------------------------------
def test_interrupt_within_spacing_is_deferred_until_window_ends() -> None:
    det = PauseDetector()
    days = [[_obs(water=0.1)]] * 2 + [[_obs(water=0.9, n=0.5)]] * 10
    fired = _run(det, days)
    # Drought on day 2; N ready on day 5 (3 days after 2) is held back, and
    # fires on day 6, the first day more than 3 days after the last interrupt.
    assert [(e.day, e.reason) for e in fired] == [(2, DROUGHT), (6, NITROGEN)]


def test_deferred_reason_is_dropped_if_condition_clears_in_window() -> None:
    det = PauseDetector()
    days = (
        [[_obs(water=0.1, n=1.0)]] * 2
        + [[_obs(water=0.9, n=0.5)]] * 3
        + [[_obs(water=0.9, n=1.0)]] * 5
    )
    fired = _run(det, days)
    assert [e.reason for e in fired] == [DROUGHT]
    assert det.latch("f1", NITROGEN).deferred is False


def test_same_day_onsets_fire_drought_then_defer_n() -> None:
    det = PauseDetector()
    both = [_obs(water=0.1, n=0.5)]
    fired = _run(det, [both] * 3 + [[_obs(water=0.9, n=0.5)]] * 5)
    assert [(e.day, e.reason) for e in fired] == [(2, DROUGHT), (6, NITROGEN)]
    gaps = [b.day - a.day for a, b in pairwise(fired)]
    assert all(g > PauseConfig().interrupt_spacing_days for g in gaps)


def test_latch_mutations_break_rarity() -> None:
    """``rearm_days=0`` makes persistent N stress fire repeatedly (mutation check)."""
    days = [[_obs(n=0.5)]] * 60
    assert len(_run(PauseDetector(), days)) == 1
    eager = PauseDetector(PauseConfig(n_rearm_days=0))
    assert len(_run(eager, days)) > 4


# ---------------------------------------------------------------------------
# Serialisation: latch, armed state and deferral survive a round trip
# ---------------------------------------------------------------------------
def test_detector_round_trip_mid_episode_continues_identically() -> None:
    days = (
        [[_obs(water=0.1, n=0.5)]] * 3  # drought fires, N deferred
        + [[_obs(water=0.9, n=0.5)]] * 7  # N fires day 6; drought re-arms
        + [[_obs(water=0.1, n=0.5)]] * 12  # drought fires again on day 12
    )
    tmin: list[float | None] = [-2.0] + [4.0] * 21
    straight = PauseDetector()
    expected = _run(straight, days, tmin=tmin)

    first = PauseDetector()
    head = _run(first, days[:3], tmin=tmin[:3])
    assert first.latch("f1", NITROGEN).deferred
    assert not first.latch("f1", DROUGHT).armed
    saved = json.loads(json.dumps(first.to_dict()))
    restored = PauseDetector.from_dict(saved)
    tail = _run(restored, days[3:], start_day=4, tmin=tmin[3:])

    assert head + tail == expected
    assert [(e.day, e.reason) for e in expected] == [
        (1, FROST),
        (2, DROUGHT),
        (6, NITROGEN),
        (12, DROUGHT),
    ]
    assert restored.to_dict() == straight.to_dict()


def test_detector_from_dict_rejects_bad_data() -> None:
    with pytest.raises(ValueError):
        PauseDetector.from_dict(
            {"latches": [{"field_id": "f1", "reason": "hail", "armed": True}]}
        )
    with pytest.raises(ValueError):
        PauseLatchState.from_dict({"run_days": -1})


def test_reset_rearms_every_reason() -> None:
    det = PauseDetector()
    _run(det, [[_obs(water=0.1)]] * 2)
    det.reset()
    assert det.to_dict() == {"latches": [], "last_interrupt_day": {}}
    assert len(_run(det, [[_obs(water=0.1)]] * 2)) == 1


def test_pause_event_round_trip() -> None:
    ev = PauseEvent(day=12, reason=NITROGEN, message="N", field_id="f2", interrupt=True)
    assert PauseEvent.from_dict(json.loads(json.dumps(ev.to_dict()))) == ev


# ---------------------------------------------------------------------------
# Real simulation: the detector reads the simulation's own stress state
# ---------------------------------------------------------------------------
def _field_and_weather(
    crop_key: str = "maize",
    climate_key: str = "netherlands_temperate",
    soil: str = "loam_temperate",
    days: int = 120,
    seed: int = 42,
) -> tuple[FieldManager, list[WeatherRecord]]:
    fm = FieldManager()
    fm.add_field(
        "f1",
        [
            PatchConfig(
                soil_profile_key=soil,
                crop_key=crop_key,
                climate_key=climate_key,
                area_fraction=1.0,
            )
        ],
    )
    climate = load_climate_presets(Path("data/climate/presets.yaml")).climates[
        climate_key
    ]
    weather = SyntheticWeatherGenerator(climate, seed=seed).generate(
        days, date(2024, 4, 1)
    )
    return fm, weather.records


def _step(fm: FieldManager, idx: int, rec: WeatherRecord) -> None:
    """One day exactly as the API's ``_run_day_step`` drives it."""
    for fld in fm.fields.values():
        for p in fld.patches:
            p.recorder.clear()
            p.recorder.set_day(idx)
    fm.step_day(
        drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
        tmin_c=rec.tmin_c,
        tmax_c=rec.tmax_c,
        shortwave_mj_m2=rec.shortwave_mj_m2 or 12.0,
        sim_date=rec.day,
    )


def test_observation_equals_the_stress_the_canopy_receives() -> None:
    """An alert reads exactly the Ks and N stress events the canopy consumes."""
    fm, weather = _field_and_weather(days=60)
    patch = fm.fields["f1"].patches[0]
    seen: dict[str, float] = {}

    def _probe(ev: BaseEvent) -> None:
        if isinstance(ev, WaterStressComputed):
            seen["water"] = ev.stress
        elif isinstance(ev, NutrientStressComputed) and ev.nutrient.upper() == "N":
            seen["n"] = ev.stress

    patch.orch.event_bus.subscribe(BaseEvent, _probe)
    for idx, rec in enumerate(weather):
        _step(fm, idx, rec)
        obs = observe_patch(patch)
        assert obs.water_stress == pytest.approx(min(1.0, max(0.0, seen["water"])))
        assert obs.n_stress == pytest.approx(min(1.0, max(0.0, seen["n"])))
        assert obs.stage == patch.orch.canopy._current_stage
        assert obs.frost_threshold_c == patch.orch.canopy.params.frost_threshold_c


def test_frost_gate_is_the_canopy_damage_gate() -> None:
    """For every stage, the canopy damages on frost iff the notice can fire."""
    from agrogame.soil.canopy.events import FrostDamageApplied
    from agrogame.soil.canopy.runtime import CanopyRuntime

    fm, _ = _field_and_weather(days=1)
    orch = fm.fields["f1"].patches[0].orch
    runtime = CanopyRuntime(orch.event_bus, orch.canopy)
    damaged: list[FrostDamageApplied] = []
    orch.event_bus.subscribe(FrostDamageApplied, damaged.append)
    threshold = orch.canopy.params.frost_threshold_c
    for stage in PhenologyStage:
        damaged.clear()
        orch.canopy._current_stage = stage
        orch.canopy.state.lai = 2.0
        runtime._check_frost_damage(threshold - 3.0)
        notice = _run(
            PauseDetector(),
            [[_obs(stage=stage, frost_threshold_c=threshold)]],
            tmin=[threshold - 3.0],
        )
        assert bool(damaged) == bool(notice), stage


def test_n_depleted_soil_raises_one_n_alert() -> None:
    """A strongly N-depleted soil trips one N alert (replaces the #351 test)."""
    fm, weather = _field_and_weather(days=100)
    orch = fm.fields["f1"].patches[0].orch
    n = len(orch.n_state.no3)
    orch.n_state.no3 = [0.0] * n
    orch.n_state.nh4 = [0.0] * n
    orch.n_state.organic_n = [x * 0.15 for x in orch.n_state.organic_n]
    if orch.som is not None:
        for layer in orch.som.state.layers:
            for pool in (layer.labile, layer.intermediate, layer.stable):
                pool.n_kg_ha *= 0.15
    det = PauseDetector()
    fired: list[PauseEvent] = []
    for idx, rec in enumerate(weather):
        _step(fm, idx, rec)
        tomorrow = weather[idx + 1].tmin_c if idx + 1 < len(weather) else None
        fired += det.observe_fields(idx + 1, fm.fields, tomorrow)
    n_alerts = [e for e in fired if e.reason is NITROGEN]
    assert len(n_alerts) == 1, fired
    assert n_alerts[0].interrupt and n_alerts[0].field_id == "f1"


def test_kenya_rice_frost_notice_from_real_weather() -> None:
    """Rice's 10 °C chilling threshold trips frost notices in the highlands."""
    fm, weather = _field_and_weather(
        crop_key="rice", climate_key="kenya_highlands", soil="clay_temperate"
    )
    det = PauseDetector()
    fired: list[PauseEvent] = []
    for idx, rec in enumerate(weather[:-1]):
        _step(fm, idx, rec)
        fired += det.observe_fields(idx + 1, fm.fields, weather[idx + 1].tmin_c)
    frost = [e for e in fired if e.reason is FROST]
    assert frost and all(not e.interrupt for e in frost)


# ---------------------------------------------------------------------------
# Turn manager: phases, plan revision, serialisation, no bus subscriptions
# ---------------------------------------------------------------------------
def test_turn_manager_phase_and_result_lifecycle() -> None:
    from agrogame.game.turn import SeasonResult

    fm, _ = _field_and_weather(days=1)
    mgr = GameTurnManager(fm.fields["f1"].patches[0].orch, crop_key="maize")
    assert mgr.phase is SeasonPhase.PLANNING and mgr.result is None
    mgr.phase = SeasonPhase.EXECUTING
    mgr.result = SeasonResult(30, 400.0, 4000.0, pause_count=2, crop_key="maize")
    mgr.phase = SeasonPhase.SETTLING
    assert mgr.result.grain_kg_ha == pytest.approx(mgr.result.grain_g_m2 * 10.0)


def test_turn_manager_revise_plan_replaces_remaining_events() -> None:
    fm, _ = _field_and_weather(days=1)
    plan = ManagementPlan(
        events=[
            ManagementEvent(day=10, action="irrigate", params={"amount_mm": 20.0}),
            ManagementEvent(day=50, action="irrigate", params={"amount_mm": 30.0}),
        ]
    )
    mgr = GameTurnManager(fm.fields["f1"].patches[0].orch, plan=plan)
    mgr.revise_plan(
        20, [ManagementEvent(day=21, action="irrigate", params={"amount_mm": 50.0})]
    )
    assert [e.day for e in mgr.plan.events] == [10, 21]
    assert fm.fields["f1"].patches[0].orch.management_plan is mgr.plan


def test_management_plan_revise() -> None:
    plan = ManagementPlan(
        events=[
            ManagementEvent(day=5, action="irrigate", params={"amount_mm": 10}),
            ManagementEvent(day=15, action="irrigate", params={"amount_mm": 20}),
            ManagementEvent(day=25, action="irrigate", params={"amount_mm": 30}),
        ]
    )
    new_events = [
        ManagementEvent(
            day=20, action="fertilize", params={"type": "urea", "amount_kg_ha": 50}
        ),
    ]
    plan.revise(from_day=10, new_events=new_events)
    assert len(plan.events) == 2
    assert plan.events[0].day == 5
    assert plan.events[1].day == 20
    assert plan.events[1].action == "fertilize"


def test_turn_manager_serialisation_round_trip() -> None:
    fm, _ = _field_and_weather(days=1)
    orch = fm.fields["f1"].patches[0].orch
    plan = ManagementPlan(
        events=[ManagementEvent(day=30, action="irrigate", params={"amount_mm": 20})]
    )
    mgr = GameTurnManager(orch, plan=plan, crop_key="maize")
    mgr.phase = SeasonPhase.PAUSED
    mgr.current_day = 42
    data = json.loads(json.dumps(mgr.to_dict()))
    restored = GameTurnManager.restore_state(data, orch)
    assert restored.phase is SeasonPhase.PAUSED
    assert restored.current_day == 42
    assert restored.crop_key == "maize"
    assert [e.day for e in restored.plan.events] == [30]


def test_turn_managers_leave_no_bus_handlers_across_seasons() -> None:
    """Replacing managers every season adds no handler to the bus (#486)."""
    fm, _ = _field_and_weather(days=1)
    bus = fm.fields["f1"].patches[0].orch.event_bus
    before = {k: len(v) for k, v in bus._handlers.items()}
    for _ in range(3):
        mgr = GameTurnManager(fm.fields["f1"].patches[0].orch)
        mgr.close()
        mgr.close()  # idempotent
    after = {k: len(v) for k, v in bus._handlers.items() if v}
    assert after == {k: v for k, v in before.items() if v}
