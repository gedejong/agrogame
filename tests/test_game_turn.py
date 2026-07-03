"""Tests for GameTurnManager (AGRO-110)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.game.turn import (
    GameTurnManager,
    PauseConfig,
    PauseEvent,
    PauseReason,
    SeasonPhase,
    SeasonResult,
)
from agrogame.plant.presets import load_crop_presets
from agrogame.sim.management import ManagementEvent, ManagementPlan
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.weather.generator import SyntheticWeatherGenerator
from agrogame.weather.presets import load_climate_presets
from agrogame.weather.types import WeatherRecord


def _make_orch_and_weather(
    days: int = 150,
    climate_name: str = "netherlands_temperate",
    seed: int = 42,
) -> tuple[FullSimulationOrchestrator, list[WeatherRecord]]:
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    climate = climates.climates[climate_name]
    crop = crops.get_preset("maize", climate_name)
    orch = FullSimulationOrchestrator(
        profile, crop=crop, latitude_deg=climate.latitude_deg
    )
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, date(2024, 4, 1))
    return orch, series.records


# ---------------------------------------------------------------------------
# AC: season completes with settlement when no pauses
# ---------------------------------------------------------------------------
def test_season_completes_no_pauses() -> None:
    orch, weather = _make_orch_and_weather(days=50)
    # High frost threshold = no frost pauses, disable drought
    cfg = PauseConfig(
        frost_temp_c=-50.0, drought_consecutive_days=999, n_deficiency_threshold=0.0
    )
    mgr = GameTurnManager(orch, weather, pause_config=cfg, crop_key="maize")

    pauses = list(mgr.run_season())
    assert len(pauses) == 0
    assert mgr.phase == SeasonPhase.SETTLING
    assert mgr.result is not None
    assert mgr.result.total_days == 50
    assert mgr.result.grain_g_m2 >= 0


# ---------------------------------------------------------------------------
# AC: frost event pauses execution
# ---------------------------------------------------------------------------
def test_frost_pauses_execution() -> None:
    orch, weather = _make_orch_and_weather(days=100)
    # Low frost threshold to trigger easily in NL spring
    cfg = PauseConfig(
        frost_temp_c=5.0, drought_consecutive_days=999, n_deficiency_threshold=0.0
    )
    mgr = GameTurnManager(orch, weather, pause_config=cfg)

    pauses = []
    for pause in mgr.run_season():
        pauses.append(pause)
        assert isinstance(pause, PauseEvent)
        assert pause.reason == PauseReason.FROST_WARNING
        # Don't revise, just continue

    assert len(pauses) > 0
    assert mgr.result is not None


# ---------------------------------------------------------------------------
# AC (#351): genuine N deficiency pauses execution
# ---------------------------------------------------------------------------
def test_nutrient_deficiency_pauses_execution() -> None:
    """A strongly N-depleted soil trips the N-deficiency pause (#351).

    With SOM as the single mineralisation source, a genuinely N-poor soil
    starves the crop, N stress collapses, and the game pauses to warn the
    player — behaviour that was inert while mineral N stayed pinned high.
    """
    orch, weather = _make_orch_and_weather(days=100)
    # Genuinely N-poor: zero mineral N and 15% of organic N in every reservoir.
    n = len(orch.n_state.no3)
    orch.n_state.no3 = [0.0] * n
    orch.n_state.nh4 = [0.0] * n
    orch.n_state.organic_n = [x * 0.15 for x in orch.n_state.organic_n]
    if orch.som is not None:
        for layer in orch.som.state.layers:
            for pool in (layer.labile, layer.intermediate, layer.stable):
                pool.n_kg_ha *= 0.15
    # Disable frost/drought so only the N pause can fire.
    cfg = PauseConfig(
        frost_temp_c=-50.0, drought_consecutive_days=999, n_deficiency_threshold=0.5
    )
    mgr = GameTurnManager(orch, weather, pause_config=cfg)

    reasons = [pause.reason for pause in mgr.run_season()]
    assert PauseReason.NUTRIENT_DEFICIENCY in reasons, (
        f"expected an N-deficiency pause on a strongly depleted soil, " f"got {reasons}"
    )


# ---------------------------------------------------------------------------
# AC: player can revise plan after pause and resume
# ---------------------------------------------------------------------------
def test_revise_plan_after_pause() -> None:
    orch, weather = _make_orch_and_weather(days=100)
    plan = ManagementPlan(
        events=[
            ManagementEvent(day=10, action="irrigate", params={"amount_mm": 20.0}),
            ManagementEvent(day=50, action="irrigate", params={"amount_mm": 30.0}),
        ]
    )
    cfg = PauseConfig(
        frost_temp_c=5.0, drought_consecutive_days=999, n_deficiency_threshold=0.0
    )
    mgr = GameTurnManager(orch, weather, plan=plan, pause_config=cfg)

    revised = False
    for pause in mgr.run_season():
        if not revised:
            # Replace remaining events with emergency irrigation
            mgr.revise_plan(
                pause.day + 1,
                [
                    ManagementEvent(
                        day=pause.day + 1,
                        action="irrigate",
                        params={"amount_mm": 50.0},
                    )
                ],
            )
            revised = True
        # Continue execution after revision

    assert revised
    assert mgr.result is not None


# ---------------------------------------------------------------------------
# AC: ManagementPlan.revise
# ---------------------------------------------------------------------------
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
    # day 5 kept, day 15 and 25 removed, day 20 added
    assert len(plan.events) == 2
    assert plan.events[0].day == 5
    assert plan.events[1].day == 20
    assert plan.events[1].action == "fertilize"


# ---------------------------------------------------------------------------
# AC: serialization round-trip mid-season
# ---------------------------------------------------------------------------
def test_serialization_mid_season() -> None:
    orch, weather = _make_orch_and_weather(days=100)
    plan = ManagementPlan(
        events=[
            ManagementEvent(day=30, action="irrigate", params={"amount_mm": 20}),
        ]
    )
    cfg = PauseConfig(
        frost_temp_c=5.0, drought_consecutive_days=999, n_deficiency_threshold=0.0
    )
    mgr = GameTurnManager(orch, weather, plan=plan, pause_config=cfg, crop_key="maize")

    # Run until first pause
    gen = mgr.run_season()
    _ = next(gen)
    assert mgr.phase == SeasonPhase.PAUSED

    # Save state
    d = mgr.to_dict()
    assert d["phase"] == "paused"
    assert d["current_day"] > 0
    assert d["crop_key"] == "maize"

    # Restore into a new manager
    orch2, weather2 = _make_orch_and_weather(days=100)
    restored = GameTurnManager.restore_state(d, orch2, weather2)
    assert restored.current_day == mgr.current_day
    assert restored.phase == SeasonPhase.PAUSED
    assert restored.crop_key == "maize"


# ---------------------------------------------------------------------------
# AC: season phases transition correctly
# ---------------------------------------------------------------------------
def test_phase_transitions() -> None:
    orch, weather = _make_orch_and_weather(days=20)
    cfg = PauseConfig(
        frost_temp_c=-50.0, drought_consecutive_days=999, n_deficiency_threshold=0.0
    )
    mgr = GameTurnManager(orch, weather, pause_config=cfg)

    assert mgr.phase == SeasonPhase.PLANNING
    list(mgr.run_season())
    assert mgr.phase == SeasonPhase.SETTLING


# ---------------------------------------------------------------------------
# AC: SeasonResult fields
# ---------------------------------------------------------------------------
def test_season_result_fields() -> None:
    orch, weather = _make_orch_and_weather(days=30)
    cfg = PauseConfig(
        frost_temp_c=-50.0, drought_consecutive_days=999, n_deficiency_threshold=0.0
    )
    mgr = GameTurnManager(orch, weather, pause_config=cfg, crop_key="maize")
    list(mgr.run_season())

    r = mgr.result
    assert r is not None
    assert isinstance(r, SeasonResult)
    assert r.total_days == 30
    assert r.grain_kg_ha == pytest.approx(r.grain_g_m2 * 10.0)
    assert r.crop_key == "maize"
