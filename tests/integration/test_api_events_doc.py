"""``docs/api-events.md`` agrees with a real ``/step`` event stream (#426).

Every fenced ``json`` block in the reference is a whole event as ``/step``
sends it, and each is checked against a real event of the same ``event_type``:
the same envelope keys, the same ``module`` and the same ``data`` keys. Every
``*Computed`` diagnostic the stream carries must have a row. A renamed, added
or dropped payload field, or a new diagnostic, fails here instead of leaving
the reference silently wrong.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.state import games  # noqa: E402

DOC = Path(__file__).resolve().parents[2] / "docs" / "api-events.md"
_JSON_BLOCK = re.compile(r"^```json\n(.*?)^```", re.MULTILINE | re.DOTALL)
DAYS = 10
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
EXAMPLES = [json.loads(block) for block in _JSON_BLOCK.findall(DOC.read_text())]


@pytest.fixture(scope="module")
def step_events() -> dict[str, dict]:
    """The first ``/step`` event of each type over ``DAYS`` days of a fresh game."""
    games.clear()
    client = TestClient(create_app())
    gid = client.post("/api/v1/games", json=GAME).json()["game_id"]
    setup = client.post(f"/api/v1/games/{gid}/start-season?days=150&seed=42")
    assert setup.status_code == 200, setup.text
    resp = client.post(f"/api/v1/games/{gid}/step?days={DAYS}")
    assert resp.status_code == 200, resp.text
    first: dict[str, dict] = {}
    for snap in resp.json()["daily_snapshots"]:
        for ev in snap["events"]:
            first.setdefault(ev["event_type"], ev)
    return first


def test_the_reference_shows_an_evapotranspiration_payload() -> None:
    assert "EvapotranspirationComputed" in {ex["event_type"] for ex in EXAMPLES}


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda ex: ex["event_type"])
def test_doc_example_matches_a_real_step_event(
    example: dict, step_events: dict[str, dict]
) -> None:
    real = step_events.get(example["event_type"])
    assert real is not None, f"no {example['event_type']} in {DAYS} stepped days"
    assert set(example) == set(real)
    assert example["module"] == real["module"]
    assert set(example["data"]) == set(real["data"])


def test_every_computed_diagnostic_on_step_has_a_row(
    step_events: dict[str, dict],
) -> None:
    doc = DOC.read_text()
    computed = [name for name in step_events if name.endswith("Computed")]
    assert "EvapotranspirationComputed" in computed
    assert [name for name in computed if f"| `{name}` |" not in doc] == []
