"""Identical games give byte-identical ``/step`` responses (#562).

Two sources used to make every run's bytes unique: ``DayTick.drivers`` went out
as ``<...DailyDrivers object at 0x...>`` and every event carried its wall-clock
emit ``timestamp``. Each play below is a fresh app and session store, run for
two seasons through ``/start-season`` and chunked ``/step`` calls, as the
client drives it (#487).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.state import games  # noqa: E402
from agrogame.params.phenology import PhenologyStage  # noqa: E402

SEASONS = 2
SEASON_DAYS = 60
CHUNK_DAYS = 20
GAME = {
    "fields": [
        {
            "field_id": "f1",
            "patches": [
                {
                    "soil_profile_key": "loam_temperate",
                    "crop_key": "maize",
                    "climate_key": "netherlands_temperate",
                    "area_fraction": 1.0,
                }
            ],
        }
    ],
    "starting_credits": 10000,
}
DRIVER_FIELDS = {
    "rainfall_mm",
    "irrigation_mm",
    "evaporation_mm",
    "rainfall_intensity_mm_hr",
}


def _play() -> list[bytes]:
    """Every ``/step`` response body of one fresh game, in order."""
    games.clear()
    client = TestClient(create_app())
    gid = client.post("/api/v1/games", json=GAME).json()["game_id"]
    bodies: list[bytes] = []
    for _ in range(SEASONS):
        setup = client.post(
            f"/api/v1/games/{gid}/start-season?days={SEASON_DAYS}&seed=42"
        )
        assert setup.status_code == 200, setup.text
        complete = False
        while not complete:
            resp = client.post(f"/api/v1/games/{gid}/step?days={CHUNK_DAYS}")
            assert resp.status_code == 200, resp.text
            bodies.append(resp.content)
            complete = resp.json()["season_complete"]
    return bodies


@pytest.fixture(scope="module")
def plays() -> tuple[list[bytes], list[bytes]]:
    return _play(), _play()


def _snapshots(bodies: list[bytes]) -> list[dict]:
    return [snap for b in bodies for snap in json.loads(b)["daily_snapshots"]]


def test_identical_runs_give_byte_identical_step_responses(
    plays: tuple[list[bytes], list[bytes]],
) -> None:
    first, second = plays
    assert len(first) == len(second) == SEASONS * SEASON_DAYS // CHUNK_DAYS
    for i, (a, b) in enumerate(zip(first, second, strict=True)):
        assert a == b, f"/step response {i} differs between identical runs"


def test_no_event_payload_is_a_python_repr(
    plays: tuple[list[bytes], list[bytes]],
) -> None:
    first, _ = plays
    for body in first:
        assert b" object at 0x" not in body
    events = [ev for snap in _snapshots(first) for ev in snap["events"]]
    assert events
    assert not [ev for ev in events if "timestamp" in ev["data"]]


def test_day_tick_drivers_carry_the_days_rainfall(
    plays: tuple[list[bytes], list[bytes]],
) -> None:
    """The water and ET phases' drivers are data: that day's rain, as stepped."""
    snaps = _snapshots(plays[0])
    assert len(snaps) == SEASONS * SEASON_DAYS
    for snap in snaps:
        ticks = [ev for ev in snap["events"] if ev["event_type"] == "DayTick"]
        assert ticks, f"day {snap['day_number']} recorded no DayTick"
        for tick in ticks:
            data = tick["data"]
            assert data["sim_date"] == snap["date"]
            if data["phase"] not in ("water", "et"):
                assert data["drivers"] is None
                continue
            assert set(data["drivers"]) == DRIVER_FIELDS
            assert round(data["drivers"]["rainfall_mm"], 1) == snap["rain_mm"]


def test_stage_changes_carry_stage_values(
    plays: tuple[list[bytes], list[bytes]],
) -> None:
    values = {s.value for s in PhenologyStage}
    changes = [
        ev["data"]
        for snap in _snapshots(plays[0])
        for ev in snap["events"]
        if ev["event_type"] == "StageChanged"
    ]
    assert changes, "no stage change in the window; lengthen SEASON_DAYS"
    for change in changes:
        assert {change["from_stage"], change["to_stage"]} <= values
