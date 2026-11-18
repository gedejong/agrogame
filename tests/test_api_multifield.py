"""Two-field API contract (#547, child B1 of #472).

Every test plays the Kenya two-field game of the #472 refinement: ``field_1``
is loam_temperate maize and ``field_2`` clay_temperate rice, both under
``kenya_highlands`` with the default seed-42 weather. A *control* is a second
game created from the same body that skips the action under test.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("fastapi") or not importlib.util.find_spec("httpx"),
    reason="fastapi or httpx not installed",
)

_START_CREDITS = 10000
_CLIMATE = "kenya_highlands"


def _patch(soil: str, crop: str, climate: str = _CLIMATE) -> dict[str, Any]:
    return {
        "soil_profile_key": soil,
        "crop_key": crop,
        "climate_key": climate,
        "area_fraction": 1.0,
    }


_FIELD_1 = {"field_id": "field_1", "patches": [_patch("loam_temperate", "maize")]}
_FIELD_2 = {"field_id": "field_2", "patches": [_patch("clay_temperate", "rice")]}

# The fixed two-field flow behind the ledger and save/load tests (AC4, AC5):
# ``(day, field_id, action, params)``, each taken before that day is stepped.
# Day 70 falls after the day-60 save, so the ledger is exercised across a load.
# The maize is harvested on day 168, before it matures (day 172 on seed 42), so
# the flow stays inside one season and no season-end settlement enters the
# ledger: every credit is a harvest the test made. ``_advance`` asserts that.
_FLOW = (
    (0, "field_1", "fertilize", {"type": "urea", "amount_kg_ha": 50.0}),
    (0, "field_2", "irrigate", {"amount_mm": 20.0}),
    (30, "field_1", "irrigate", {"amount_mm": 15.0}),
    (70, "field_2", "fertilize", {"type": "urea", "amount_kg_ha": 30.0}),
    (165, "field_2", "harvest", {"patch_idx": 0}),
    (168, "field_1", "harvest", {"patch_idx": 0}),
)
_SAVE_DAY = 60
_CONTINUE_DAYS = 20
_FLOW_END = 169


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app
    from agrogame.api.state import games

    games.clear()
    return TestClient(create_app())


def _create(client, fields: list[dict] | None = None) -> dict[str, Any]:
    resp = client.post(
        "/api/v1/games",
        json={
            "fields": fields if fields is not None else [_FIELD_1, _FIELD_2],
            "starting_credits": _START_CREDITS,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _step(client, game_id: str, days: int) -> dict[str, Any]:
    resp = client.post(f"/api/v1/games/{game_id}/step?days={days}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _act(
    client, game_id: str, field_id: str, action: str, params: dict
) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": field_id, "action": action, "params": params},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "executed"
    return resp.json()


def _forecast(client, game_id: str, field_id: str | None = None) -> dict[str, Any]:
    query = "" if field_id is None else f"?field_id={field_id}"
    resp = client.get(f"/api/v1/games/{game_id}/forecast{query}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _crops(client, game_id: str) -> dict[str, list[str]]:
    fields = client.get(f"/api/v1/games/{game_id}").json()["fields"]
    return {fid: [p["crop_key"] for p in patches] for fid, patches in fields.items()}


def _balance(client, game_id: str) -> int:
    return client.get(f"/api/v1/games/{game_id}").json()["balance_credits"]


def _projection(body: dict[str, Any]) -> list[tuple[float, float]]:
    return [(d["water_stress"], d["mineral_n_kg_ha"]) for d in body["forecast"]]


def _weather(body: dict[str, Any]) -> list[tuple[str, float, float, float]]:
    return [
        (d["date"], d["tmin_c"], d["tmax_c"], d["rain_mm"]) for d in body["forecast"]
    ]


# ---------------------------------------------------------------------------
# AC1: the forecast follows the requested field
# ---------------------------------------------------------------------------
def _assert_forecast_is_field_scoped(client, game_id: str) -> None:
    unscoped = _forecast(client, game_id)
    field_1 = _forecast(client, game_id, "field_1")
    field_2 = _forecast(client, game_id, "field_2")
    assert field_1 == unscoped
    assert _projection(field_1) != _projection(field_2)
    # Weather is farm-level: only the soil/crop projection differs.
    assert _weather(field_1) == _weather(field_2)
    assert len(field_1["forecast"]) == 5


def test_forecast_projects_the_requested_field(client) -> None:
    game_id = _create(client)["game_id"]
    _step(client, game_id, 30)
    _assert_forecast_is_field_scoped(client, game_id)


def test_forecast_stays_field_scoped_in_the_second_season(client) -> None:
    """The season reset replants both fields; the forecast still follows the id."""
    game_id = _create(client)["game_id"]
    assert _step(client, game_id, 200)["season_complete"]
    second = _step(client, game_id, 30)
    assert second["day_number"] == 30
    _assert_forecast_is_field_scoped(client, game_id)


def test_forecast_without_field_id_projects_the_first_field(client) -> None:
    """The default is the first field in creation order, not the id ``field_1``."""
    game_id = _create(client, [_FIELD_2, _FIELD_1])["game_id"]
    _step(client, game_id, 30)
    assert _forecast(client, game_id) == _forecast(client, game_id, "field_2")
    assert _forecast(client, game_id) != _forecast(client, game_id, "field_1")


def test_forecast_unknown_field_is_404_without_side_effects(client) -> None:
    from agrogame.api.state import games

    game_id = _create(client)["game_id"]
    resp = client.get(f"/api/v1/games/{game_id}/forecast?field_id=field_9")
    assert resp.status_code == 404
    assert "field_9" in resp.json()["detail"]
    # The lookup precedes weather generation, so a 404 leaves the session as is.
    assert games[game_id].weather == []


# ---------------------------------------------------------------------------
# AC2: creation guards
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("fields", "named"),
    [
        pytest.param(
            [_FIELD_1, {"field_id": "field_1", "patches": _FIELD_2["patches"]}],
            ["field_1"],
            id="duplicate-field-id",
        ),
        pytest.param(
            [_FIELD_1, {"field_id": "field_2", "patches": []}],
            ["field_2"],
            id="field-without-patches",
        ),
        pytest.param(
            [
                _FIELD_1,
                {
                    "field_id": "field_2",
                    "patches": [
                        _patch("clay_temperate", "maize", "netherlands_temperate")
                    ],
                },
            ],
            ["kenya_highlands", "netherlands_temperate"],
            id="two-climates-across-fields",
        ),
        pytest.param(
            [
                {
                    "field_id": "field_1",
                    "patches": [
                        {**_patch("loam_temperate", "maize"), "area_fraction": 0.5},
                        {
                            **_patch("loam_temperate", "maize", "sahel_arid"),
                            "area_fraction": 0.5,
                        },
                    ],
                }
            ],
            ["kenya_highlands", "sahel_arid"],
            id="two-climates-in-one-field",
        ),
    ],
)
def test_create_rejects_an_unholdable_game_with_422(
    client, fields: list[dict], named: list[str]
) -> None:
    from agrogame.api.state import games

    _create(client)
    before = len(games)
    resp = client.post(
        "/api/v1/games",
        json={"fields": fields, "starting_credits": _START_CREDITS},
    )
    assert resp.status_code == 422, resp.text
    assert len(games) == before
    detail = resp.json()["detail"]
    for name in named:
        assert name in detail


# ---------------------------------------------------------------------------
# AC3: actions reach only their own field
# ---------------------------------------------------------------------------
_COMPARED_KEYS = ("soil_theta_surface", "som_total_c_g_m2", "lai")


def test_irrigating_field_2_leaves_field_1_as_the_control(client) -> None:
    """AC3(a). Irrigated on day 90, not day 0.

    On day 0 the Kenya clay profile sits at field capacity and the cascading
    bucket drains the 20 mm through within the day, so field_2's theta comes
    out identical to the control (only its leached NO3 differs). By day 90 the
    profile has dried below field capacity and the water stays.
    """
    game_id = _create(client)["game_id"]
    control_id = _create(client)["game_id"]
    _step(client, game_id, 90)
    _step(client, control_id, 90)
    _act(client, game_id, "field_2", "irrigate", {"amount_mm": 20.0})
    got = _step(client, game_id, 1)["patches"]
    want = _step(client, control_id, 1)["patches"]

    for mine, ref in zip(got["field_1"], want["field_1"], strict=True):
        for key in _COMPARED_KEYS:
            assert mine[key] == ref[key], key
    assert got["field_2"][0]["soil_theta_surface"] > (
        want["field_2"][0]["soil_theta_surface"]
    )


def test_fertilising_field_1_leaves_field_2_as_the_control(client) -> None:
    """AC3(b): urea 50 kg N/ha on field_1, then one day."""
    game_id = _create(client)["game_id"]
    control_id = _create(client)["game_id"]
    _act(client, game_id, "field_1", "fertilize", {"type": "urea", "amount_kg_ha": 50})
    got = _step(client, game_id, 1)["patches"]
    want = _step(client, control_id, 1)["patches"]

    assert got["field_2"][0]["soil_state"]["n_no3"] == (
        want["field_2"][0]["soil_state"]["n_no3"]
    )
    # Positive control: the urea did land on field_1.
    assert got["field_1"][0]["soil_state"]["n_nh4"] != (
        want["field_1"][0]["soil_state"]["n_nh4"]
    )


def test_harvesting_field_2_leaves_field_1_standing(client) -> None:
    """AC3(c): harvest the rice on day 165, with no ``/report`` call."""
    game_id = _create(client)["game_id"]
    day = _step(client, game_id, 165)
    assert day["day_number"] == 165
    field_1_grain = day["patches"]["field_1"][0]["grain_g_m2"]
    field_2_grain = day["patches"]["field_2"][0]["grain_g_m2"]

    harvest = _act(client, game_id, "field_2", "harvest", {"patch_idx": 0})
    assert harvest["grain_g_m2"] == field_2_grain
    assert harvest["revenue_credits"] > 0
    assert _crops(client, game_id) == {"field_1": ["maize"], "field_2": [""]}

    after = _step(client, game_id, 1)["patches"]
    assert after["field_1"][0]["grain_g_m2"] >= field_1_grain > 0.0


def test_planting_field_2_charges_the_preview_and_leaves_field_1(client) -> None:
    """AC3(d): plant sorghum on field_2 patch 0."""
    game_id = _create(client)["game_id"]
    fields_before = client.get(f"/api/v1/games/{game_id}").json()["fields"]
    balance_before = _balance(client, game_id)
    body = {
        "field_id": "field_2",
        "action": "plant",
        "params": {"crop_key": "sorghum", "patch_idx": 0},
    }
    preview = client.post(f"/api/v1/games/{game_id}/action/preview", json=body)
    assert preview.status_code == 200, preview.text

    planted = _act(client, game_id, "field_2", "plant", body["params"])
    assert planted["cost_credits"] == preview.json()["cost_credits"] > 0
    assert planted["balance_credits"] == balance_before - planted["cost_credits"]

    fields_after = client.get(f"/api/v1/games/{game_id}").json()["fields"]
    assert [p["crop_key"] for p in fields_after["field_2"]] == ["sorghum"]
    assert fields_after["field_1"] == fields_before["field_1"]


@pytest.mark.parametrize("route", ["action", "action/preview"])
def test_an_unknown_field_is_404_and_charges_nothing(client, route: str) -> None:
    """AC3(e)."""
    game_id = _create(client)["game_id"]
    balance_before = _balance(client, game_id)
    resp = client.post(
        f"/api/v1/games/{game_id}/{route}",
        json={"field_id": "field_9", "action": "irrigate", "params": {"amount_mm": 20}},
    )
    assert resp.status_code == 404
    assert _balance(client, game_id) == balance_before


# ---------------------------------------------------------------------------
# AC4 + AC5: one flow across both fields, saved and loaded at day 60
# ---------------------------------------------------------------------------
def _advance(
    client, game_id: str, start: int, end: int, actions: list[dict]
) -> dict[str, Any]:
    """Play ``_FLOW`` from day ``start`` to ``end``; return the last ``/step``."""
    day = start
    last: dict[str, Any] = {}
    for at, field_id, action, params in _FLOW:
        if not start <= at < end:
            continue
        if at > day:
            last = _step(client, game_id, at - day)
            assert not last["season_complete"], last["day_number"]
            day = at
        actions.append(_act(client, game_id, field_id, action, params))
    if end > day:
        last = _step(client, game_id, end - day)
        assert not last["season_complete"], last["day_number"]
    return last


def _rel_bounds() -> dict[str, float]:
    """``_REL_BOUNDS`` of the save-continuation suite (#515), loaded by path."""
    path = Path(__file__).parent / "integration" / "test_save_continuation.py"
    spec = importlib.util.spec_from_file_location("_save_continuation", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module._REL_BOUNDS)


@pytest.fixture(scope="module")
def flow(tmp_path_factory) -> dict[str, Any]:
    """Run ``_FLOW`` once with a save/load at day 60, beside an unsaved control."""
    from fastapi.testclient import TestClient

    from agrogame.api import routes
    from agrogame.api.app import create_app
    from agrogame.api.state import games

    games.clear()
    client = TestClient(create_app())
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(routes, "_SAVE_DIR", tmp_path_factory.mktemp("saves"))

        control_id = _create(client)["game_id"]
        end = _SAVE_DAY + _CONTINUE_DAYS
        control = _advance(client, control_id, 0, end, [])["patches"]

        created = _create(client)
        game_id = created["game_id"]
        actions: list[dict] = []
        _advance(client, game_id, 0, _SAVE_DAY, actions)
        saved = client.get(f"/api/v1/games/{game_id}").json()
        assert client.post(f"/api/v1/games/{game_id}/save").status_code == 200
        games.clear()
        assert client.post(f"/api/v1/games/{game_id}/load").status_code == 200
        loaded = client.get(f"/api/v1/games/{game_id}").json()
        continued = _advance(client, game_id, _SAVE_DAY, end, actions)["patches"]
        _advance(client, game_id, end, _FLOW_END, actions)
        final_balance = _balance(client, game_id)
    games.clear()
    return {
        "created": created,
        "actions": actions,
        "saved": saved,
        "loaded": loaded,
        "continued": continued,
        "control": control,
        "final_balance": final_balance,
    }


def test_ledger_reconciles_across_fields(flow: dict[str, Any]) -> None:
    """AC4: create, actions on both fields, a Harvest of each field."""
    harvests = [a for a in flow["actions"] if a["action"] == "harvest"]
    assert len(flow["actions"]) == len(_FLOW)
    assert len(harvests) == 2
    assert all(h["revenue_credits"] > 0 for h in harvests)

    created_balance = flow["created"]["balance_credits"]
    expected = (
        _START_CREDITS
        - (_START_CREDITS - created_balance)
        - sum(a["cost_credits"] for a in flow["actions"])
        + sum(h["revenue_credits"] for h in harvests)
    )
    assert flow["final_balance"] == expected


def test_save_load_round_trips_fields_and_balance(flow: dict[str, Any]) -> None:
    """AC5: ``fields`` and ``balance_credits`` survive ``games.clear()``."""
    assert flow["loaded"]["fields"] == flow["saved"]["fields"]
    assert flow["loaded"]["balance_credits"] == flow["saved"]["balance_credits"]


def test_save_load_continues_within_the_continuation_bounds(
    flow: dict[str, Any],
) -> None:
    """AC5: 20 days after the load, each field tracks the unsaved control."""
    bounds = _rel_bounds()
    for field_id in ("field_1", "field_2"):
        got = flow["continued"][field_id][0]
        want = flow["control"][field_id][0]
        assert got["grain_g_m2"] == pytest.approx(
            want["grain_g_m2"], rel=bounds["grain"]
        ), field_id
        assert got["som_total_c_g_m2"] == pytest.approx(
            want["som_total_c_g_m2"], rel=bounds["som"]
        ), field_id
