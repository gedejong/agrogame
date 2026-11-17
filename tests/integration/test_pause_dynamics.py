"""In-season pause dynamics on every catalog scenario, through the API (#470).

Each scenario in ``game/scripts/scenario_catalog.gd`` is played for two
consecutive seasons per seed (42 and 43) exactly as the client will drive it:
``/step`` with ``stop_on_pause=true``, resuming after every stop. The bounds
asserted here are the refined acceptance criteria of #470 (ADR-017). They
check game-alert behaviour, not crop science: (a) is a rarity judgement, and
(b)-(e) follow from the trigger design.

A control replays seed 42 with detection disabled and plain ``/step`` calls,
and requires the simulation to be identical to 1e-9: observing and stopping
must change nothing.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("fastapi") or not importlib.util.find_spec("httpx"),
    reason="fastapi or httpx not installed",
)

CATALOG = Path("game/scripts/scenario_catalog.gd")
SEEDS = (42, 43)
SEASONS = 2
MAX_INTERRUPTS_PER_SEASON = 4  # (a): judgement, anchored on ADR-004's ~5 min season
SPACING_DAYS = 3  # (e)
FROST_GATE = {"emerged", "vegetative", "flowering"}  # (c)
N_GATE = {"emerged", "vegetative", "flowering"}  # (d)


def _catalog() -> list[tuple[str, list[dict[str, Any]]]]:
    """Scenario labels and patch configs parsed from the Godot catalog."""
    text = CATALOG.read_text(encoding="utf-8")
    body = text.split("const SCENARIOS", 1)[1]
    scenarios = []
    for chunk in re.split(r'"label":\s*', body)[1:]:
        label = re.match(r'"([^"]+)"', chunk)
        assert label is not None
        patches = []
        for block in re.findall(r"\{[^{}]*\}", chunk):
            pairs = dict(re.findall(r'"(\w+)":\s*("[^"]*"|[\d.]+)', block))
            patches.append(
                {
                    "soil_profile_key": pairs["soil_profile_key"].strip('"'),
                    "crop_key": pairs["crop_key"].strip('"'),
                    "climate_key": pairs["climate_key"].strip('"'),
                    "area_fraction": float(pairs["area_fraction"]),
                }
            )
        scenarios.append((label.group(1), patches))
    return scenarios


SCENARIOS = _catalog()
LABELS = [label for label, _ in SCENARIOS]


@dataclass
class Season:
    """One season's alerts, per-day stages and final simulation state."""

    events: list[dict[str, Any]] = field(default_factory=list)
    stages: dict[tuple[str, int], set[str]] = field(default_factory=dict)
    status_events: list[dict[str, Any]] = field(default_factory=list)
    final: dict[str, Any] = field(default_factory=dict)


def _final_state(game_id: str) -> dict[str, Any]:
    from agrogame.api.state import games

    s = games[game_id]
    state: dict[str, Any] = {"balance": s.ledger.balance_credits}
    for fid, fld in s.field_manager.fields.items():
        for i, p in enumerate(fld.patches):
            snap = p.orch.snapshot_soil()
            state[f"{fid}/{i}"] = {
                "grain": p.orch.canopy.state.grain_biomass_g_m2,
                "biomass": p.orch.canopy.state.biomass_g_m2,
                "lai": p.orch.canopy.state.lai,
                "no3": list(snap.n_no3),
                "nh4": list(snap.n_nh4),
                "theta": list(snap.water_theta),
            }
    return state


def _new_game(client, patches: list[dict[str, Any]]) -> str:
    resp = client.post(
        "/api/v1/games",
        json={"fields": [{"field_id": "field_1", "patches": patches}]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["game_id"]


def _play_season(client, game_id: str, seed: int, stop: bool) -> Season:
    from agrogame.api.state import DEFAULT_SEASON_DAYS

    season = Season()
    remaining = DEFAULT_SEASON_DAYS
    query = "&stop_on_pause=true" if stop else ""
    while remaining:
        resp = client.post(
            f"/api/v1/games/{game_id}/step?days={remaining}&seed={seed}{query}"
        )
        assert resp.status_code == 200, resp.text
        r = resp.json()
        season.events += r["pause_events"]
        for snap in r["daily_snapshots"]:
            key = (snap["field_id"], snap["day_number"])
            season.stages.setdefault(key, set()).add(snap["crop_stage"])
        remaining = r["days_remaining"]
    status = client.get(f"/api/v1/games/{game_id}/status").json()
    season.status_events = status["pause_events"]
    assert status["season_result"]["pause_count"] == sum(
        1 for e in season.events if e["interrupt"]
    )
    season.final = _final_state(game_id)
    return season


def _play(client, patches, seed: int, detect: bool) -> list[Season]:
    from agrogame.api.state import games

    game_id = _new_game(client, patches)
    if not detect:
        games[game_id].pause_detector = None
    return [_play_season(client, game_id, seed, stop=detect) for _ in range(SEASONS)]


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app

    return TestClient(create_app())


@pytest.fixture(scope="module")
def runs(client) -> dict[tuple[str, int], list[Season]]:
    from agrogame.api.state import games

    played = {}
    for label, patches in SCENARIOS:
        for seed in SEEDS:
            played[(label, seed)] = _play(client, patches, seed, detect=True)
            games.clear()
    return played


def _seasons(runs, label: str | None = None):
    for (lab, seed), seasons in runs.items():
        if label is None or lab == label:
            for n, season in enumerate(seasons, start=1):
                yield f"{lab} seed {seed} season {n}", season


def _interrupts_by_field(season: Season) -> dict[str, list[int]]:
    days: dict[str, list[int]] = {}
    for e in season.events:
        if e["interrupt"]:
            days.setdefault(e["field_id"], []).append(e["day"])
    return days


def test_catalog_is_parsed() -> None:
    assert len(SCENARIOS) >= 6
    assert all(patches for _, patches in SCENARIOS)
    assert any("Sahel" in label for label in LABELS)


def test_a_interrupts_per_season_per_field_are_rare(runs) -> None:
    for name, season in _seasons(runs):
        for fid, days in _interrupts_by_field(season).items():
            assert len(days) <= MAX_INTERRUPTS_PER_SEASON, (name, fid, season.events)


def test_b_sahel_sorghum_gets_a_drought_pause_every_season(runs) -> None:
    sahel = next(label for label in LABELS if "Sahel" in label)
    for name, season in _seasons(runs, sahel):
        drought = [e for e in season.events if e["reason"] == "drought"]
        assert drought and all(e["interrupt"] for e in drought), name


def test_c_frost_notices_only_in_canopy_damage_stages(runs) -> None:
    for name, season in _seasons(runs):
        for e in season.events:
            if e["reason"] != "frost_warning":
                continue
            assert e["interrupt"] is False, (name, e)
            assert season.stages[(e["field_id"], e["day"])] & FROST_GATE, (name, e)


def test_d_n_pauses_only_in_the_response_window(runs) -> None:
    for name, season in _seasons(runs):
        for e in season.events:
            if e["reason"] == "nutrient_deficiency":
                assert season.stages[(e["field_id"], e["day"])] & N_GATE, (name, e)


def test_e_interrupts_on_a_field_are_more_than_three_days_apart(runs) -> None:
    for name, season in _seasons(runs):
        for fid, days in _interrupts_by_field(season).items():
            gaps = [b - a for a, b in pairwise(days)]
            assert all(g > SPACING_DAYS for g in gaps), (name, fid, days)


def test_no_duplicate_alerts_within_or_across_seasons(runs) -> None:
    for name, season in _seasons(runs):
        keys = [(e["field_id"], e["reason"], e["day"]) for e in season.events]
        assert len(keys) == len(set(keys)), name
        # /status lists exactly this season's alerts, nothing carried over.
        assert season.status_events == season.events, name


@pytest.mark.parametrize("label", LABELS)
def test_detection_changes_no_simulation_value(client, runs, label) -> None:
    """Detection on with stops, versus off with plain steps: identical to 1e-9."""
    from agrogame.api.state import games

    patches = dict(SCENARIOS)[label]
    control = _play(client, patches, SEEDS[0], detect=False)
    games.clear()
    for observed, plain in zip(runs[(label, SEEDS[0])], control, strict=True):
        assert plain.events == []
        assert observed.final.keys() == plain.final.keys()
        for key, value in plain.final.items():
            if isinstance(value, dict):
                for var, expected in value.items():
                    assert observed.final[key][var] == pytest.approx(
                        expected, abs=1e-9, rel=0
                    ), (label, key, var)
            else:
                assert observed.final[key] == value, (label, key)
