"""Tests for FastAPI game API (AGRO-111)."""

from __future__ import annotations

import importlib.util

import pytest

# Skip all tests if fastapi or httpx not installed
pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("fastapi") or not importlib.util.find_spec("httpx"),
    reason="fastapi or httpx not installed",
)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from agrogame.api.app import create_app
    from agrogame.api.state import games

    games.clear()
    app = create_app()
    return TestClient(app)


def _create_game(client) -> str:
    resp = client.post(
        "/api/v1/games",
        json={
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
        },
    )
    assert resp.status_code == 200
    return resp.json()["game_id"]


# ---------------------------------------------------------------------------
# AC: full lifecycle — create, plan, run, get results
# ---------------------------------------------------------------------------
def test_full_lifecycle(client) -> None:
    game_id = _create_game(client)

    # Submit plan
    resp = client.post(
        f"/api/v1/games/{game_id}/plan",
        json={
            "field_id": "f1",
            "events": [
                {"day": 10, "action": "irrigate", "params": {"amount_mm": 20}},
                {
                    "day": 30,
                    "action": "fertilize",
                    "params": {"type": "urea", "amount_kg_ha": 50},
                },
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["event_count"] == 2

    # Start season
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=50&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_days"] == 50

    # Get status with results
    resp = client.get(f"/api/v1/games/{game_id}/status")
    assert resp.status_code == 200
    status = resp.json()
    assert status["phase"] == "settling"


# ---------------------------------------------------------------------------
# AC: create game returns correct structure
# ---------------------------------------------------------------------------
def test_create_game(client) -> None:
    resp = client.post(
        "/api/v1/games",
        json={
            "fields": [
                {
                    "field_id": "field_1",
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
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "game_id" in data
    assert data["phase"] == "planning"
    assert data["field_count"] == 1
    assert data["balance_credits"] == 10000


# ---------------------------------------------------------------------------
# AC: get game state
# ---------------------------------------------------------------------------
def test_get_game(client) -> None:
    game_id = _create_game(client)
    resp = client.get(f"/api/v1/games/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["game_id"] == game_id
    assert resp.json()["phase"] == "planning"


# ---------------------------------------------------------------------------
# AC: 404 for nonexistent game
# ---------------------------------------------------------------------------
def test_get_nonexistent_game(client) -> None:
    resp = client.get("/api/v1/games/nope")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC: save and load round-trip via API
# ---------------------------------------------------------------------------
def test_save_and_load_roundtrip(client) -> None:
    """Save a game, load it back, verify state preserved."""
    game_id = _create_game(client)

    # Run a short season to change state
    client.post(f"/api/v1/games/{game_id}/start-season?days=10&seed=42")

    # Get state before save
    status_before = client.get(f"/api/v1/games/{game_id}/status").json()

    # Save
    resp = client.post(f"/api/v1/games/{game_id}/save")
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"

    # Load
    resp = client.post(f"/api/v1/games/{game_id}/load")
    assert resp.status_code == 200
    assert resp.json()["status"] == "loaded"

    # Verify state restored
    status_after = client.get(f"/api/v1/games/{game_id}").json()
    assert status_after["balance_credits"] == status_before["balance_credits"]


def test_load_nonexistent_save_returns_404(client) -> None:
    resp = client.post("/api/v1/games/no-save/load")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC: CORS headers present
# ---------------------------------------------------------------------------
def test_cors_headers(client) -> None:
    resp = client.options(
        "/api/v1/games",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert "access-control-allow-origin" in resp.headers


# ---------------------------------------------------------------------------
# AC: OpenAPI docs available
# ---------------------------------------------------------------------------
def test_openapi_docs(client) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "paths" in resp.json()
    assert "/api/v1/games" in resp.json()["paths"]


# ---------------------------------------------------------------------------
# AC (AGRO-120): season response includes soil state per patch
# ---------------------------------------------------------------------------
def test_season_response_includes_soil_state(client) -> None:
    """Soil state fields present and physically plausible after season."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=50&seed=42")
    assert resp.status_code == 200
    data = resp.json()

    # Backward compat: grain_g_m2 still present
    assert "field_results" in data
    patches = data["field_results"]["f1"]
    assert len(patches) >= 1
    patch = patches[0]
    assert "grain_g_m2" in patch
    assert "grain_kg_ha" in patch

    # Soil state present
    ss = patch["soil_state"]
    assert ss is not None

    # Per-layer arrays exist and have correct length (>= 1 layer)
    assert len(ss["water_theta"]) >= 1
    assert len(ss["n_no3"]) >= 1
    assert len(ss["n_nh4"]) >= 1
    assert len(ss["p_available"]) >= 1
    assert len(ss["ph"]) >= 1
    assert len(ss["som_labile_c"]) >= 1
    assert len(ss["som_intermediate_c"]) >= 1
    assert len(ss["som_stable_c"]) >= 1
    assert len(ss["microbe_c"]) >= 1

    # Physical plausibility
    for theta in ss["water_theta"]:
        assert 0.0 <= theta <= 0.6, f"theta {theta} out of range"
    for no3 in ss["n_no3"]:
        assert no3 >= 0.0, f"NO3 {no3} negative"
    for nh4 in ss["n_nh4"]:
        assert nh4 >= 0.0, f"NH4 {nh4} negative"
    for ph_val in ss["ph"]:
        assert 3.0 <= ph_val <= 10.0, f"pH {ph_val} out of range"
    for som_c in ss["som_labile_c"]:
        assert som_c >= 0.0, f"SOM labile C {som_c} negative"

    # Aggregates
    assert ss["som_total_c_g_m2"] > 0.0, "Total SOM should be positive"
    assert 0.0 <= ss["theta_surface"] <= 0.6


def test_season_response_backward_compatible(client) -> None:
    """Existing fields (total_days, pause_count, field_results) unchanged."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=30&seed=1")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_days" in data
    assert data["total_days"] == 30
    assert "pause_count" in data
    assert "field_results" in data


def test_status_includes_soil_state(client) -> None:
    """GET /status also includes soil_state after season."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/start-season?days=30&seed=42")
    resp = client.get(f"/api/v1/games/{game_id}/status")
    assert resp.status_code == 200
    status = resp.json()
    sr = status["season_result"]
    assert sr is not None
    patch = sr["field_results"]["f1"][0]
    assert patch["soil_state"] is not None
    assert len(patch["soil_state"]["water_theta"]) >= 1


# ---------------------------------------------------------------------------
# AC (#121): multi-season date progression
# ---------------------------------------------------------------------------
def test_season_response_includes_dates(client) -> None:
    """Response includes start_date and end_date in ISO format."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=50&seed=42")
    data = resp.json()
    assert data["start_date"] == "2024-04-01"
    assert data["end_date"] == "2024-05-21"
    assert data["total_days"] == 50


def test_consecutive_seasons_advance_date(client) -> None:
    """Each /start-season continues from where the previous ended."""
    game_id = _create_game(client)

    r1 = client.post(f"/api/v1/games/{game_id}/start-season?days=50&seed=42").json()
    assert r1["start_date"] == "2024-04-01"
    assert r1["end_date"] == "2024-05-21"
    assert r1["season_number"] == 1

    r2 = client.post(f"/api/v1/games/{game_id}/start-season?days=50").json()
    assert r2["start_date"] == "2024-05-21"
    assert r2["end_date"] == "2024-07-10"
    assert r2["season_number"] == 2

    r3 = client.post(f"/api/v1/games/{game_id}/start-season?days=50").json()
    assert r3["start_date"] == "2024-07-10"
    assert r3["season_number"] == 3


def test_consecutive_seasons_produce_different_yields(client) -> None:
    """Soil state evolves between runs — yields and SOM should differ."""
    game_id = _create_game(client)

    r1 = client.post(f"/api/v1/games/{game_id}/start-season?days=100&seed=42").json()
    r2 = client.post(f"/api/v1/games/{game_id}/start-season?days=100").json()

    p1 = r1["field_results"]["f1"][0]
    p2 = r2["field_results"]["f1"][0]

    # Yields should differ (different weather seed, different soil state)
    assert p1["grain_g_m2"] != p2["grain_g_m2"], "Yields should differ between runs"

    # Soil state should evolve
    som1 = p1["soil_state"]["som_total_c_g_m2"]
    som2 = p2["soil_state"]["som_total_c_g_m2"]
    assert som1 != som2, "SOM should evolve between runs"


def test_first_season_backward_compatible(client) -> None:
    """First season with explicit seed behaves identically to old behavior."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=50&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_days"] == 50
    assert "field_results" in data
    assert data["start_date"] == "2024-04-01"
