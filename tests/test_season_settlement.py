"""End-of-season settlement happens in the season-completing ``/step`` (#518).

Run Season used to finish without paying for the standing crop: only ``GET
/report`` settled, the client never called it, and a mid-season Harvest
suppressed completion altogether. Expected revenue is computed here from the
price table's base price and quarter multiplier, never by calling a route
helper, so a wrong quarter, price or dry-matter fraction fails.
"""

from __future__ import annotations

from datetime import date

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import agrogame.api.routes as routes  # noqa: E402
from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.state import games  # noqa: E402
from agrogame.game.economy import PriceTable  # noqa: E402
from agrogame.game.turn import PauseReason  # noqa: E402

NL = "netherlands_temperate"


def _patch(crop: str, area: float, climate: str = NL, soil: str = "loam_temperate"):
    return {
        "soil_profile_key": soil,
        "crop_key": crop,
        "climate_key": climate,
        "area_fraction": area,
    }


#: The default catalog scenario: three NL maize patches.
DEFAULT = [
    _patch("maize", 0.333, soil="sandy_temperate"),
    _patch("maize", 0.334),
    _patch("maize", 0.333, soil="clay_temperate"),
]
HARVEST_0 = {"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}}


@pytest.fixture()
def client() -> TestClient:
    games.clear()
    return TestClient(create_app())


def _create(client: TestClient, fields: dict[str, list[dict]]) -> str:
    resp = client.post(
        "/api/v1/games",
        json={
            "fields": [{"field_id": f, "patches": p} for f, p in fields.items()],
            "starting_credits": 10_000,
        },
    )
    assert resp.status_code == 200, resp.text
    return str(resp.json()["game_id"])


def _start(client: TestClient, game_id: str, days: int = 150) -> dict:
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days={days}&seed=42")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _step(client: TestClient, game_id: str, days: int) -> dict:
    resp = client.post(f"/api/v1/games/{game_id}/step?days={days}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _step_query(client: TestClient, game_id: str, query: str) -> dict:
    resp = client.post(f"/api/v1/games/{game_id}/step?{query}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _settlement(patches: list, crop_key: str, end: date, dmf: float = 1.0) -> int:
    """``settle_season``'s arithmetic for one crop group, from the price table."""
    price = PriceTable.load().crop_prices[crop_key]
    per_kg = (
        price.base_credits_per_kg * price.seasonal_multipliers[(end.month - 1) // 3]
    )
    area = sum(p.config.area_fraction for p in patches)
    grain = (
        sum(
            p.orch.canopy.state.grain_biomass_g_m2 * p.config.area_fraction
            for p in patches
        )
        / area
    )
    return int(grain * 10.0 / dmf * area * per_kg)


def _ledger(game_id: str) -> tuple[int, int, int]:
    ledger = games[game_id].ledger
    return ledger.balance_credits, ledger.season_revenue, len(ledger.costs)


def test_completion_settles_every_field_at_its_own_crop(client) -> None:
    """AC1: every field, each crop group at its own price and harvest product."""
    game_id = _create(
        client,
        {
            "f1": [_patch("maize", 1.0)],
            "f2": [_patch("spring_wheat", 0.5), _patch("grape", 0.5)],
        },
    )
    _start(client, game_id)
    _step(client, game_id, 149)
    s = games[game_id]
    balance = s.ledger.balance_credits
    assert s.ledger.season_revenue == 0

    last = _step(client, game_id, 1)
    assert last["season_complete"]
    f1 = s.field_manager.fields["f1"].patches
    f2 = s.field_manager.fields["f2"].patches
    end = s.current_date
    parts = [
        _settlement(f1, "maize", end),
        _settlement(f2[:1], "spring_wheat", end),
        _settlement(f2[1:], "grape", end, dmf=0.1946),
    ]
    assert all(part > 0 for part in parts), parts
    assert s.ledger.season_revenue == sum(parts)
    assert last["balance_credits"] == balance + sum(parts) == s.ledger.balance_credits
    # The response shows the grain that was sold, not a zeroed pool.
    for fid, patches in (("f1", f1), ("f2", f2)):
        for shown, p in zip(last["patches"][fid], patches, strict=True):
            grain = p.orch.canopy.state.grain_biomass_g_m2
            assert shown["grain_g_m2"] == round(grain, 1) > 0.0


def test_mid_season_harvest_does_not_suppress_completion(client) -> None:
    """AC2/AC3: harvest patch 0 at day 120, step to 150; one completion, one sale."""
    game_id = _create(client, {"f1": DEFAULT})
    _start(client, game_id)
    _step(client, game_id, 120)
    r0 = client.post(f"/api/v1/games/{game_id}/action", json=HARVEST_0)
    assert r0.status_code == 200, r0.text
    assert _step(client, game_id, 30)["season_complete"]

    s = games[game_id]
    assert s.run_count == 1
    report = client.get(f"/api/v1/games/{game_id}/report").json()
    assert (report["season_number"], report["total_days"]) == (1, 150)
    completion = _settlement(
        s.field_manager.fields["f1"].patches[1:], "maize", s.current_date
    )
    assert completion > 0
    assert report["revenue_credits"] == r0.json()["revenue_credits"] + completion
    assert report["balance_after"] - report["balance_before"] == completion

    # /report is a read: identical bodies, ledger untouched.
    settled = _ledger(game_id)
    assert client.get(f"/api/v1/games/{game_id}/report").json() == report
    assert _ledger(game_id) == settled

    assert _start(client, game_id)["season_number"] == 2
    assert s.ledger.season_revenue == 0
    assert [c.category for c in s.ledger.costs] == ["seed", "seed"]
    assert [
        p.orch.canopy.state.grain_biomass_g_m2
        for p in s.field_manager.fields["f1"].patches
    ] == [0.0] * 3


def test_stepping_on_after_maturity_completion_credits_nothing(client) -> None:
    """AC2: NL spring wheat completes at maturity; later days pay nothing more."""
    game_id = _create(client, {"f1": [_patch("spring_wheat", 1.0)]})
    _start(client, game_id)
    s = games[game_id]
    while not _step(client, game_id, 5)["season_complete"]:
        pass
    assert s.day_index < 150, "completion was maturity-triggered"
    assert s.run_count == 1
    settled = _ledger(game_id)
    assert settled[1] > 0

    last = _step(client, game_id, 150 - s.day_index)
    assert last["season_complete"]
    assert s.run_count == 1
    assert _ledger(game_id) == settled
    assert last["balance_credits"] == settled[0]


def test_harvest_then_report_settles_nothing(client) -> None:
    """AC4: a mid-season /report after a Harvest only reads (the client's path)."""
    game_id = _create(client, {"f1": DEFAULT})
    _start(client, game_id)
    _step(client, game_id, 120)
    r0 = client.post(f"/api/v1/games/{game_id}/action", json=HARVEST_0).json()
    standing = [
        p.orch.canopy.state.grain_biomass_g_m2
        for p in games[game_id].field_manager.fields["f1"].patches
    ]
    before = _ledger(game_id)

    report = client.get(f"/api/v1/games/{game_id}/report").json()
    assert report["revenue_credits"] == r0["revenue_credits"]
    assert client.get(f"/api/v1/games/{game_id}/report").json() == report
    assert _ledger(game_id) == before
    after = [
        p.orch.canopy.state.grain_biomass_g_m2
        for p in games[game_id].field_manager.fields["f1"].patches
    ]
    assert after == standing


def test_run_season_then_harvest_is_refused_each_cycle(client) -> None:
    """AC4: after completion Harvest and its preview are 400 and charge nothing."""
    game_id = _create(client, {"f1": DEFAULT})
    s = games[game_id]
    for cycle in (1, 2):
        _start(client, game_id)
        if cycle == 2:
            # A new season re-enables Harvest until it completes again.
            _step(client, game_id, 10)
            assert (
                client.post(
                    f"/api/v1/games/{game_id}/action/preview", json=HARVEST_0
                ).status_code
                == 200
            )
            assert not s.season_completed
        _step(client, game_id, 150 - s.day_index)
        settled = _ledger(game_id)
        for path in ("action", "action/preview"):
            for params in ({"patch_idx": 0}, {}):
                body = {"field_id": "f1", "action": "harvest", "params": params}
                resp = client.post(f"/api/v1/games/{game_id}/{path}", json=body)
                assert resp.status_code == 400, (cycle, path, params)
                assert resp.json()["detail"] == "Season settled: start the next season"
        assert _ledger(game_id) == settled
        assert [p.config.crop_key for p in s.field_manager.fields["f1"].patches] == [
            "maize"
        ] * 3


def test_completed_season_survives_save_and_load(client, tmp_path, monkeypatch) -> None:
    """AC6/AC4: the settled ledger and the completion flag survive a save/load.

    Grain is left standing after settlement, so the persisted flag is the only
    thing stopping a Harvest after load from paying for it twice.
    """
    monkeypatch.setattr(routes, "_SAVE_DIR", tmp_path)
    game_id = _create(client, {"f1": DEFAULT})
    _start(client, game_id)
    _step(client, game_id, 150)
    settled = _ledger(game_id)
    assert settled[1] > 0
    assert client.post(f"/api/v1/games/{game_id}/save").status_code == 200

    games.clear()
    assert client.post(f"/api/v1/games/{game_id}/load").status_code == 200
    assert _ledger(game_id) == settled
    assert games[game_id].season_completed

    resp = client.post(f"/api/v1/games/{game_id}/action", json=HARVEST_0)
    assert resp.status_code == 400, resp.text
    assert _ledger(game_id) == settled


def _save_and_load(client: TestClient, game_id: str) -> None:
    assert client.post(f"/api/v1/games/{game_id}/save").status_code == 200
    games.clear()
    assert client.post(f"/api/v1/games/{game_id}/load").status_code == 200


def test_alert_latches_and_settlement_survive_save_and_load(
    client, tmp_path, monkeypatch
) -> None:
    """#470's latch keys and #518's completion flag round-trip together.

    NL loam maize raises its N alert mid-season. The game is saved and loaded
    just after it, with the N latch fired, and again after completion. The
    alert log survives both loads, the N alert does not fire a second time, and
    the season is settled exactly once: by the completing /step, not by a load.
    """
    monkeypatch.setattr(routes, "_SAVE_DIR", tmp_path)
    game_id = _create(client, {"f1": [_patch("maize", 1.0)]})
    _start(client, game_id)
    first = _step_query(client, game_id, "days=150&stop_on_pause=true")
    events = first["pause_events"]
    assert [e["reason"] for e in events] == ["nutrient_deficiency"], events

    _save_and_load(client, game_id)
    latch = games[game_id].pause_detector.latch("f1", PauseReason.NUTRIENT_DEFICIENCY)
    assert not latch.armed, "the fired N latch was reloaded re-armed"
    assert not games[game_id].season_completed
    last = _step(client, game_id, first["days_remaining"])
    assert last["season_complete"]
    events += last["pause_events"]
    s = games[game_id]
    settled = _ledger(game_id)
    once = _settlement(s.field_manager.fields["f1"].patches, "maize", s.current_date)
    assert settled[1] == once > 0

    _save_and_load(client, game_id)
    assert games[game_id].season_completed
    assert _ledger(game_id) == settled
    status = client.get(f"/api/v1/games/{game_id}/status").json()
    assert status["pause_events"] == events
    keys = [(e["field_id"], e["reason"], e["day"]) for e in events]
    assert len(keys) == len(set(keys)), "an alert fired twice"
    assert [e["reason"] for e in events].count("nutrient_deficiency") == 1

    resp = client.post(f"/api/v1/games/{game_id}/action", json=HARVEST_0)
    assert resp.status_code == 400, resp.text
    assert _ledger(game_id) == settled


def test_two_kenya_maize_cycles_settle_at_their_quarters(client) -> None:
    """AC5/AC7: two Run Season cycles (start, then step), no /report calls.

    Season 1 ends on 2024-08-29 and is paid at maize's Q3 multiplier (0.8);
    season 2 ends on 2025-01-26 and is paid at Q1 (1.1).
    """
    game_id = _create(client, {"f1": [_patch("maize", 1.0, "kenya_highlands")]})
    s = games[game_id]
    patches = s.field_manager.fields["f1"].patches
    multipliers = PriceTable.load().crop_prices["maize"].seasonal_multipliers
    revenues: list[int] = []
    costs = 0
    for cycle, end, quarter, multiplier in (
        (1, date(2024, 8, 29), 3, 0.8),
        (2, date(2025, 1, 26), 1, 1.1),
    ):
        assert _start(client, game_id)["season_number"] == cycle
        last = _step(client, game_id, 150)
        assert last["season_complete"]
        assert s.current_date == end
        assert multipliers[quarter - 1] == multiplier
        expected = _settlement(patches, "maize", end)
        assert expected > 0
        assert s.ledger.season_revenue == expected
        assert last["balance_credits"] == s.ledger.balance_credits
        revenues.append(expected)
        costs += sum(c.amount_credits for c in s.ledger.costs)
    assert s.ledger.balance_credits == 10_000 + sum(revenues) - costs
