"""Tests covering missing lines in agrogame/sim/engine.py."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agrogame.sim.engine import (
    ActionType,
    EventScheduler,
    ScheduledAction,
    SeasonResults,
    SimulationEngine,
)


# ---------------------------------------------------------------------------
# EventScheduler
# ---------------------------------------------------------------------------


def test_event_scheduler_snapshot_roundtrip() -> None:
    """Cover lines 50-53 (snapshot) and 59-70 (from_snapshot)."""
    sched = EventScheduler()
    sched.schedule(
        ScheduledAction(day_index=0, action=ActionType.IRRIGATION, amount=5.0)
    )
    sched.schedule(
        ScheduledAction(
            day_index=1, action=ActionType.FERTILIZER_AN, amount=40.0, layer=1
        )
    )
    snap = sched.snapshot()
    assert 0 in snap
    assert 1 in snap

    restored = EventScheduler.from_snapshot(snap)
    assert len(restored.for_day(0)) == 1
    assert restored.for_day(0)[0].action is ActionType.IRRIGATION
    assert restored.for_day(1)[0].layer == 1


# ---------------------------------------------------------------------------
# SimulationEngine — helper to create a small weather file
# ---------------------------------------------------------------------------


def _write_weather_csv(tmp_path: Path, n_days: int = 10) -> Path:
    p = tmp_path / "weather.csv"
    lines = ["date,tmin_c,tmax_c,rh_pct,wind_m_s,rs_mj_m2,rn_mj_m2,precip_mm"]
    for i in range(n_days):
        d = date(2024, 6, 1 + i).isoformat()
        lines.append(f"{d},10,25,60,2.0,18,14,3")
    p.write_text("\n".join(lines))
    return p


@pytest.fixture
def engine(tmp_path: Path) -> SimulationEngine:
    from agrogame.soil.loader import load_soil_presets

    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    weather = _write_weather_csv(tmp_path, n_days=10)
    return SimulationEngine(profile, weather, max_days=10)


# ---------------------------------------------------------------------------
# Control methods
# ---------------------------------------------------------------------------


def test_pause_and_resume(engine: SimulationEngine) -> None:
    """Cover lines 111 and 114."""
    engine.pause()
    assert engine.is_running is False
    engine.resume()
    assert engine.is_running is True


# ---------------------------------------------------------------------------
# Scheduling helpers
# ---------------------------------------------------------------------------


def test_schedule_fertilizer_an(engine: SimulationEngine) -> None:
    """Cover line 127."""
    engine.schedule_fertilizer_an(2, 50.0, layer=0)
    items = engine.scheduler.for_day(2)
    assert any(a.action is ActionType.FERTILIZER_AN for a in items)


def test_schedule_fertilizer_urea(engine: SimulationEngine) -> None:
    """Cover line 139."""
    engine.schedule_fertilizer_urea(3, 30.0, layer=1)
    items = engine.scheduler.for_day(3)
    assert any(a.action is ActionType.FERTILIZER_UREA for a in items)


def test_schedule_lime(engine: SimulationEngine) -> None:
    """Cover line 149."""
    engine.schedule_lime(4, 200.0, layer=0)
    items = engine.scheduler.for_day(4)
    assert any(a.action is ActionType.LIME for a in items)


def test_schedule_harvest(engine: SimulationEngine) -> None:
    """Cover line 159."""
    engine.schedule_harvest(5)
    items = engine.scheduler.for_day(5)
    assert any(a.action is ActionType.HARVEST for a in items)


# ---------------------------------------------------------------------------
# Checkpoint / Restore
# ---------------------------------------------------------------------------


def test_checkpoint_and_restore(engine: SimulationEngine) -> None:
    """Cover lines 170, 178-182."""
    engine.schedule_irrigation(1, 10.0)
    engine.current_day = 3
    engine.is_running = True
    engine.days_per_step = 2

    cp = engine.checkpoint()
    assert cp["current_day"] == 3
    assert cp["is_running"] is True
    assert cp["days_per_step"] == 2

    # Create fresh engine and restore
    engine.current_day = 0
    engine.is_running = False
    engine.days_per_step = 1
    engine.restore(cp)
    assert engine.current_day == 3
    assert engine.is_running is True
    assert engine.days_per_step == 2


# ---------------------------------------------------------------------------
# Run season with actions
# ---------------------------------------------------------------------------


def test_run_season_basic(engine: SimulationEngine) -> None:
    """Cover lines 199, 208, 232, and the main loop."""
    result = engine.run_season()
    assert isinstance(result, SeasonResults)
    assert result.days_processed > 0
    assert result.finished


def test_run_season_with_all_actions(engine: SimulationEngine) -> None:
    """Cover lines 239-259 (_apply_action branches)."""
    engine.schedule_irrigation(0, 10.0)
    engine.schedule_fertilizer_an(1, 50.0, layer=0)
    engine.schedule_fertilizer_urea(2, 30.0, layer=0)
    engine.schedule_lime(3, 100.0, layer=0)
    engine.schedule_harvest(4)
    result = engine.run_season()
    assert result.finished


def test_advance_day_past_end(engine: SimulationEngine) -> None:
    """Cover early return in advance_day (line 199)."""
    engine.current_day = engine.max_days
    engine.advance_day()
    assert engine.current_day == engine.max_days
