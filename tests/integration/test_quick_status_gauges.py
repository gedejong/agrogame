"""What the Quick Status gauges read, through the real ``/step`` reply (#660 B8).

Water is today's Ks (the last ``WaterStressComputed.stress``), Nutrients the
minimum ``NutrientStressComputed.stress`` over N, P, S, Fe, Zn and Mn, Growth
``growth_vs_potential`` (actual over potential-production shoot biomass; van
Ittersum & Rabbinge 1997) and Root-zone water ``root_zone_water_fraction``
against 1 - p (FAO-56 Eq. 82-83, Table 22). Seeds 42-51 as in
``test_post_maturity.py``; the default 200-day season from 2024-04-01.

- Managed NL crops (urea 120 kg N/ha on day 1 and 80 on day 35, 30 mm of
  irrigation before any day the root-zone fraction is below 0.6) read healthy
  on every standing day: no gauge warns on a crop that needs nothing.
- Unmanaged Kenya maize is N- or S-limited and behind its potential by day 70;
  unmanaged Sahel maize on loam is short of water by day 21 and far behind its
  potential by day 45: stressed crops do warn.
"""

from __future__ import annotations

from functools import cache
from typing import Any

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from agrogame.api.app import create_app  # noqa: E402
from agrogame.api.state import games  # noqa: E402

SEEDS = range(42, 52)
SEASON = 200
STANDING = frozenset({"emerged", "vegetative", "flowering", "grain_fill"})
# ADR-017 n_stress_threshold applies in these stages only.
N_GATED = frozenset({"emerged", "vegetative", "flowering"})
NL = "netherlands_temperate"
MANAGED = {
    "maize": ("clay_temperate", "maize"),
    "wheat": ("clay_netherlands", "spring_wheat"),
    "grape": ("loam_temperate", "grape"),
}
_CLIENT = TestClient(create_app())


def _new_game(fields: dict[str, tuple[str, str]], climate: str) -> str:
    body = {
        "fields": [
            {
                "field_id": fid,
                "patches": [
                    {
                        "soil_profile_key": soil,
                        "crop_key": crop,
                        "climate_key": climate,
                        "area_fraction": 1.0,
                    }
                ],
            }
            for fid, (soil, crop) in fields.items()
        ],
        "starting_credits": 10**7,
    }
    resp = _CLIENT.post("/api/v1/games", json=body)
    assert resp.status_code == 200, resp.text
    gid: str = resp.json()["game_id"]
    return gid


def _step(gid: str, seed: int, days: int = 1) -> dict[str, Any]:
    resp = _CLIENT.post(f"/api/v1/games/{gid}/step?days={days}&seed={seed}")
    assert resp.status_code == 200, resp.text
    reply: dict[str, Any] = resp.json()
    return reply


def _act(gid: str, fid: str, action: str, **params: float | str) -> None:
    body = {"field_id": fid, "action": action, "params": params}
    resp = _CLIENT.post(f"/api/v1/games/{gid}/action", json=body)
    assert resp.status_code == 200, resp.text


def _gauges(patch: dict[str, Any]) -> dict[str, Any]:
    """The four gauge inputs, read as the client reads them."""
    ks = 1.0
    nutrients: dict[str, float] = {}
    for ev in patch["events"]:
        if ev["event_type"] == "WaterStressComputed":
            ks = ev["data"]["stress"]
        elif ev["event_type"] == "NutrientStressComputed":
            nutrients[ev["data"]["nutrient"]] = ev["data"]["stress"]
    return {
        "stage": patch["crop_stage"],
        "ks": ks,
        "nutrients": nutrients,
        "growth": patch["growth_vs_potential"],
        "rzf": patch["root_zone_water_fraction"],
        "p": patch["depletion_fraction_p"],
    }


@cache
def _managed(seed: int) -> dict[str, list[dict[str, Any]]]:
    games.clear()
    gid = _new_game(MANAGED, NL)
    days: dict[str, list[dict[str, Any]]] = {fid: [] for fid in MANAGED}
    rzf = dict.fromkeys(MANAGED, 1.0)
    for day in range(1, SEASON + 1):
        for fid in MANAGED:
            if day in (1, 35):
                _act(
                    gid,
                    fid,
                    "fertilize",
                    type="urea",
                    amount_kg_ha=120.0 if day == 1 else 80.0,
                )
            if rzf[fid] < 0.6:
                _act(gid, fid, "irrigate", amount_mm=30.0)
        reply = _step(gid, seed)
        for fid in MANAGED:
            g = _gauges(reply["patches"][fid][0])
            rzf[fid] = g["rzf"]
            days[fid].append(g)
    return days


def test_managed_nl_crops_read_healthy_on_every_standing_day() -> None:
    for seed in SEEDS:
        for fid, days in _managed(seed).items():
            standing = [g for g in days if g["stage"] in STANDING]
            assert standing, (seed, fid)
            dry = 0
            for g in standing:
                where = (seed, fid, g)
                assert g["growth"] >= 0.99, where
                assert g["ks"] >= 0.70, where
                assert set(g["nutrients"]) == {"N", "P", "S", "Fe", "Zn", "Mn"}, where
                assert min(g["nutrients"].values()) >= 0.70, where
                if g["stage"] in N_GATED:
                    assert g["nutrients"]["N"] >= 0.90, where
                dry += g["rzf"] < 1.0 - g["p"]
            assert dry <= 1, (seed, fid, dry)


def test_unmanaged_kenya_maize_is_nutrient_limited_and_behind_by_day_70() -> None:
    for seed in SEEDS:
        games.clear()
        gid = _new_game({"f1": ("loam_temperate", "maize")}, "kenya_highlands")
        g = _gauges(_step(gid, seed, days=70)["patches"]["f1"][0])
        assert min(g["nutrients"].values()) < 0.70, (seed, g)
        assert g["growth"] < 0.70, (seed, g)


def test_unmanaged_sahel_loam_maize_is_dry_by_day_21_and_behind_by_day_45() -> None:
    for seed in SEEDS:
        games.clear()
        gid = _new_game({"f1": ("loam_temperate", "maize")}, "sahel_arid")
        day21 = _gauges(_step(gid, seed, days=21)["patches"]["f1"][0])
        assert day21["ks"] < 0.40, (seed, day21)
        day45 = _gauges(_step(gid, seed, days=24)["patches"]["f1"][0])
        assert day45["growth"] < 0.40, (seed, day45)


def test_new_fields_on_unemerged_and_bare_patches() -> None:
    """B3, B5: None before emergence and on a bare patch; p is the crop's."""
    games.clear()
    gid = _new_game({"f1": ("loam_temperate", "maize")}, NL)
    g = _gauges(_step(gid, 42)["patches"]["f1"][0])
    assert (g["stage"], g["growth"], g["p"]) == ("planted", None, 0.55)
    assert 0.0 < g["rzf"]
    _act(gid, "f1", "harvest")
    bare = _gauges(_step(gid, 42)["patches"]["f1"][0])
    assert (bare["stage"], bare["growth"], bare["p"]) == ("", None, None)
    assert 0.0 < bare["rzf"]
