"""A crashing simulation handler fails ``/step`` with a 500 (#606).

``EventBus.emit`` used to swallow handler exceptions, so ``/step`` returned 200
while that day's physics was silently dropped. The handler error now
propagates, and the app maps it to a 500 naming the handler and the event type.
"""

from __future__ import annotations

import importlib.util
import logging

import pytest

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("fastapi") or not importlib.util.find_spec("httpx"),
    reason="fastapi or httpx not installed",
)

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


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app
    from agrogame.api.state import games

    games.clear()
    return TestClient(create_app())


class _BrokenWaterStressReader:
    """Stands in for a simulation handler with a bug."""

    def on_water_stress(self, ev: object) -> None:
        raise ValueError("internal detail that must not reach the client")


def _subscribe_broken_handler(game_id: str) -> None:
    from agrogame.api.state import games
    from agrogame.plant.events import WaterStressComputed

    patch = games[game_id].field_manager.fields["f1"].patches[0]
    patch.orch.event_bus.subscribe(
        WaterStressComputed, _BrokenWaterStressReader().on_water_stress
    )


def _assert_names_broken_handler(resp) -> None:
    assert resp.status_code == 500, resp.text
    body = resp.json()
    assert set(body) == {"detail", "handler", "event_type"}
    # The innermost handler wins: WaterStressComputed is emitted from inside
    # ETRuntime's DayTick handler, and the error names the reader, not ET.
    assert body["handler"] == f"{__name__}._BrokenWaterStressReader.on_water_stress"
    assert body["event_type"] == "WaterStressComputed"
    assert "ValueError" in body["detail"]
    assert body["handler"] in body["detail"]
    # Handler and event names only: no traceback, no exception message.
    assert "Traceback" not in resp.text
    assert "internal detail" not in resp.text


def test_step_returns_500_naming_the_failing_handler(
    client, caplog: pytest.LogCaptureFixture
) -> None:
    game_id = client.post("/api/v1/games", json=GAME).json()["game_id"]
    _subscribe_broken_handler(game_id)

    with caplog.at_level(logging.ERROR, logger="agrogame.api.app"):
        resp = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")

    _assert_names_broken_handler(resp)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert f"/api/v1/games/{game_id}/step" in errors[0].getMessage()
    # The server log keeps the traceback, with the original exception chained.
    assert errors[0].exc_info is not None
    assert isinstance(errors[0].exc_info[1].__cause__, ValueError)


def test_step_500_after_a_season_rollover(client) -> None:
    # Two seasons: the crop reset clears and re-wires the bus, and a handler
    # failure in season 2 still surfaces rather than being swallowed.
    game_id = client.post("/api/v1/games", json=GAME).json()["game_id"]
    for season in (1, 2):
        setup = client.post(f"/api/v1/games/{game_id}/start-season?days=5&seed=42")
        assert setup.status_code == 200, setup.text
        assert setup.json()["season_number"] == season
        if season == 1:
            step = client.post(f"/api/v1/games/{game_id}/step?days=5")
            assert step.status_code == 200, step.text
            assert step.json()["season_complete"] is True

    _subscribe_broken_handler(game_id)
    _assert_names_broken_handler(client.post(f"/api/v1/games/{game_id}/step?days=1"))
