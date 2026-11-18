"""``docs/api-events.md`` agrees with the engine's events (#426).

Every fenced ``json`` block in the reference is a whole event as ``/step``
sends it, and each is checked against a real event of the same ``event_type``:
the same envelope keys, the same ``module`` and the same ``data`` keys. Every
field a table row names must be a field of that event. Every ``*Computed``
diagnostic the engine defines, found by code discovery rather than by stepping
a season, must have a row. A renamed, added or dropped payload field, or a new
diagnostic, fails here instead of leaving the reference silently wrong.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import fields
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
# #562's serialisation test, whose discovery finds every BaseEvent subclass.
_SERIALISATION_TEST = (
    Path(__file__).resolve().parents[1] / "unit" / "test_api_event_serialisation.py"
)
# The count of *Computed types at #426: a floor, so an empty discovery fails.
_MIN_COMPUTED_TYPES = 8
# *Computed types deliberately left out of the reference, each with its reason.
# Empty: every diagnostic the engine defines is documented.
_UNDOCUMENTED_COMPUTED: dict[str, str] = {}
# A table row: event names in the first cell, the fields they share in the second.
_ROW = re.compile(r"^\| ((?:`[A-Z]\w+`(?:, )?)+) \| (.+?) \| ", re.MULTILINE)
_FIELD_NAME = re.compile(r"[a-z_][a-z0-9_]*")
_TYPE_WORDS = {"bool", "float", "int", "null", "object", "str"}


@pytest.fixture(scope="module")
def event_fields() -> dict[str, set[str]]:
    """Payload field names per event class name, over every discovered class.

    Discovery is ``_engine_event_types`` of the serialisation test, loaded by
    path. ``CanopyIntercepted`` and ``CanopyEvaporated`` are each defined twice;
    their fields are pooled.
    """
    spec = importlib.util.spec_from_file_location(
        "_event_serialisation", _SERIALISATION_TEST
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered first: its dataclasses resolve their annotations through it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    by_name: dict[str, set[str]] = {}
    for cls in module._engine_event_types():
        names = {f.name for f in fields(cls)} - {"timestamp"}
        by_name.setdefault(cls.__name__, set()).update(names)
    return by_name


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


def test_every_field_a_row_names_is_on_its_event(
    event_fields: dict[str, set[str]],
) -> None:
    """Rows in the type tables and the client table name real payload fields.

    A row may list a subset of its event's fields (Key Fields), never one the
    event does not carry.
    """
    rows = _ROW.findall(DOC.read_text())
    assert len(rows) >= 40
    wrong = []
    for events, cell in rows:
        for event in re.findall(r"`(\w+)`", events):
            assert event in event_fields, f"row for unknown event {event}"
            for token in re.findall(r"`([^`]+)`", cell):
                name = token.split(":")[0].strip()
                if _FIELD_NAME.fullmatch(name) and name not in _TYPE_WORDS:
                    if name not in event_fields[event]:
                        wrong.append((event, name))
    assert wrong == []


def test_every_computed_diagnostic_has_a_row(
    event_fields: dict[str, set[str]],
) -> None:
    """Every ``*Computed`` type the engine defines has a row.

    Taken from code discovery, not a stepped window: ``MassFlowNSupplyComputed``
    first reaches ``/step`` on day 20, after ``DAYS``.
    """
    computed = {name for name in event_fields if name.endswith("Computed")}
    assert len(computed) >= _MIN_COMPUTED_TYPES
    assert set(_UNDOCUMENTED_COMPUTED) <= computed
    doc = DOC.read_text()
    documented = computed - set(_UNDOCUMENTED_COMPUTED)
    assert sorted(n for n in documented if f"| `{n}` |" not in doc) == []
