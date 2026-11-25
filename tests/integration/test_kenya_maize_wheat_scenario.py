"""Two seasons of the "Kenya highlands: maize and wheat" scenario (#658).

``_FIELDS`` mirrors the catalog entry in ``game/scripts/scenario_catalog.gd``
(label "Kenya highlands: maize and wheat"): ``field_1`` loam_temperate maize,
``field_2`` clay_temperate spring_wheat, both under ``kenya_highlands`` with the
default seed-42 weather. The sowings, 2024-04-01 and the replant on 2024-10-18,
fall inside the FAO Crop Calendar windows for Kenya, *Wheat, bread*
(AEZ LH1-LH4, updated 26 Feb 2021). Bands are the realism matrix's unfertilised
Kenya spring-wheat bands (``scripts/validate_realism_matrix.py``, CROP_BANDS).
"""

from __future__ import annotations

import importlib.util
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("fastapi") or not importlib.util.find_spec("httpx"),
    reason="fastapi or httpx not installed",
)

_CLIMATE = "kenya_highlands"
_MATURITY_DAYS = (110, 175)  # matrix maturity_warn
_GRAIN_G_M2 = (200.0, 900.0)  # matrix grain_warn


def _patch(soil: str, crop: str) -> dict[str, Any]:
    return {
        "soil_profile_key": soil,
        "crop_key": crop,
        "climate_key": _CLIMATE,
        "area_fraction": 1.0,
    }


_FIELD_1 = {"field_id": "field_1", "patches": [_patch("loam_temperate", "maize")]}
_FIELD_2 = {
    "field_id": "field_2",
    "patches": [_patch("clay_temperate", "spring_wheat")],
}


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app
    from agrogame.api.state import games

    games.clear()
    return TestClient(create_app())


def _post(client, url: str, body: dict | None = None) -> dict[str, Any]:
    resp = client.post(f"/api/v1/games{url}", json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _act(client, game_id: str, action: str, params: dict) -> dict[str, Any]:
    out = _post(
        client,
        f"/{game_id}/action",
        {"field_id": "field_2", "action": action, "params": params},
    )
    assert out["status"] == "executed"
    return out


def _season(client, game_id: str) -> tuple[list[dict], dict]:
    """Step 200 days, return field_2's snapshots and its harvest reply."""
    step = _post(client, f"/{game_id}/step?days=200")
    snaps = [s for s in step["daily_snapshots"] if s["field_id"] == "field_2"]
    assert len(snaps) == 200
    return snaps, _act(client, game_id, "harvest", {"patch_idx": 0})


def _frost_days(snaps: list[dict]) -> int:
    return sum(
        e["event_type"] == "FrostDamageApplied" for s in snaps for e in s["events"]
    )


def test_wheat_field_matures_and_settles_in_two_seasons(client) -> None:
    game_id = _post(
        client, "", {"fields": [_FIELD_1, _FIELD_2], "starting_credits": 10000}
    )["game_id"]
    first, harvest_1 = _season(client, game_id)
    _act(client, game_id, "plant", {"crop_key": "spring_wheat", "patch_idx": 0})
    second, harvest_2 = _season(client, game_id)

    for snaps, harvest, quarter in ((first, harvest_1, 4), (second, harvest_2, 2)):
        # (a) matures inside the matrix band, grain inside its band, no frost.
        mature = [s for s in snaps if s["crop_stage"] == "maturity"]
        assert mature, "no maturity snapshot within 200 days"
        assert _MATURITY_DAYS[0] <= mature[0]["day_number"] <= _MATURITY_DAYS[1]
        assert _GRAIN_G_M2[0] <= harvest["grain_g_m2"] <= _GRAIN_G_M2[1]
        assert _frost_days(snaps) == 0
        # (c) one wheat grain settlement, dry_kg_ha = 10 x grain_g_m2.
        (settled,) = harvest["settlements"]
        assert settled["crop_key"] == "spring_wheat"
        assert settled["product"] == "grain"
        assert settled["quarter"] == quarter
        # grain_g_m2 is rounded to 0.1 g/m2, so x10 is exact only to 0.5 kg/ha.
        assert settled["dry_kg_ha"] == pytest.approx(
            10 * harvest["grain_g_m2"], abs=0.5
        )

    # (b) the replant starts from a fresh crop.
    assert second[0]["crop_stage"] == "planted"
    assert second[0]["dev_stage"] < 0.05


def test_field_1_maize_is_independent_of_the_wheat_field(client) -> None:
    """(d) field_1's season-1 grain equals a one-field game of the same patch."""
    both = _post(
        client, "", {"fields": [_FIELD_1, _FIELD_2], "starting_credits": 10000}
    )
    alone = _post(client, "", {"fields": [_FIELD_1], "starting_credits": 10000})
    grain = []
    for game in (both, alone):
        _post(client, f"/{game['game_id']}/step?days=200")
        out = _post(
            client,
            f"/{game['game_id']}/action",
            {"field_id": "field_1", "action": "harvest", "params": {"patch_idx": 0}},
        )
        grain.append(out["grain_g_m2"])
    assert grain[0] == pytest.approx(grain[1], abs=1e-9)
    assert grain[0] > 0
