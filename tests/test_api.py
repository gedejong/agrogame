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
def test_save_and_load_roundtrip(client, tmp_path, monkeypatch) -> None:
    """Save a game to disk, load it back, verify state preserved."""
    monkeypatch.setenv("AGROGAME_SAVE_DIR", str(tmp_path))
    # Reload the save dir in routes
    import agrogame.api.routes as _routes

    monkeypatch.setattr(_routes, "_SAVE_DIR", tmp_path)

    game_id = _create_game(client)

    # Run a short season to change state
    client.post(f"/api/v1/games/{game_id}/start-season?days=10&seed=42")

    # Get state before save
    status_before = client.get(f"/api/v1/games/{game_id}/status").json()

    # Save
    resp = client.post(f"/api/v1/games/{game_id}/save")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "saved"
    assert "path" in data

    # Verify file exists on disk
    save_path = tmp_path / f"{game_id}.agrosave.json"
    assert save_path.exists()

    # Load
    resp = client.post(f"/api/v1/games/{game_id}/load")
    assert resp.status_code == 200
    assert resp.json()["status"] == "loaded"

    # Verify state restored
    status_after = client.get(f"/api/v1/games/{game_id}").json()
    assert status_after["balance_credits"] == status_before["balance_credits"]


def test_load_nonexistent_save_returns_404(client, tmp_path, monkeypatch) -> None:
    import agrogame.api.routes as _routes

    monkeypatch.setattr(_routes, "_SAVE_DIR", tmp_path)
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


# ---------------------------------------------------------------------------
# AC (#122): multi-patch field with different soil types
# ---------------------------------------------------------------------------
def _create_multi_patch_game(client) -> str:
    resp = client.post(
        "/api/v1/games",
        json={
            "fields": [
                {
                    "field_id": "f1",
                    "patches": [
                        {
                            "soil_profile_key": "sandy_temperate",
                            "crop_key": "maize",
                            "climate_key": "netherlands_temperate",
                            "area_fraction": 0.333,
                        },
                        {
                            "soil_profile_key": "loam_temperate",
                            "crop_key": "maize",
                            "climate_key": "netherlands_temperate",
                            "area_fraction": 0.334,
                        },
                        {
                            "soil_profile_key": "clay_temperate",
                            "crop_key": "maize",
                            "climate_key": "netherlands_temperate",
                            "area_fraction": 0.333,
                        },
                    ],
                }
            ],
        },
    )
    assert resp.status_code == 200
    return resp.json()["game_id"]


def test_multi_patch_returns_three_patches(client) -> None:
    """3-patch game returns per-patch results with different soil states."""
    game_id = _create_multi_patch_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=100&seed=42")
    assert resp.status_code == 200
    patches = resp.json()["field_results"]["f1"]
    assert len(patches) == 3

    # Each patch should have soil_state
    for p in patches:
        assert p["soil_state"] is not None

    # Sandy and clay should differ in moisture (clay holds more)
    sandy_theta = patches[0]["soil_state"]["theta_surface"]
    clay_theta = patches[2]["soil_state"]["theta_surface"]
    assert (
        sandy_theta != clay_theta
    ), f"Sandy θ={sandy_theta} should differ from clay θ={clay_theta}"

    # SOM should differ (clay starts with higher OM%)
    sandy_som = patches[0]["soil_state"]["som_total_c_g_m2"]
    clay_som = patches[2]["soil_state"]["som_total_c_g_m2"]
    assert (
        sandy_som != clay_som
    ), f"Sandy SOM={sandy_som} should differ from clay SOM={clay_som}"


# ---------------------------------------------------------------------------
# AC (#125): day-by-day game loop
# ---------------------------------------------------------------------------
def test_step_one_day(client) -> None:
    """POST /step advances 1 day and returns day result."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?seed=42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["day_number"] == 1
    assert data["date"] == "2024-04-02"
    assert "weather" in data
    assert data["weather"]["tmin_c"] is not None
    assert data["weather"]["rain_mm"] >= 0
    assert "f1" in data["patches"]
    patch = data["patches"]["f1"][0]
    assert "crop_stage" in patch
    assert "soil_theta_surface" in patch
    assert data["season_complete"] is False


def test_step_multiple_days(client) -> None:
    """POST /step?days=10 advances 10 days."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=10&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["day_number"] == 10
    assert data["date"] == "2024-04-11"


def test_step_daily_snapshots(client) -> None:
    """POST /step?days=5 returns daily_snapshots for all intermediate days."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    snaps = data["daily_snapshots"]
    # 5 days × 1 patch = 5 snapshots
    assert len(snaps) == 5, f"Expected 5 snapshots, got {len(snaps)}"
    # Each snapshot has required fields
    for s in snaps:
        assert "day_number" in s
        assert "date" in s
        assert "field_id" in s
        assert "patch_idx" in s
        assert "lai" in s
        assert "water_stress" in s
        assert "soil_theta_surface" in s
        assert "n_available_total" in s
        assert "rain_mm" in s
    # Day numbers should be 1-5
    day_nums = [s["day_number"] for s in snaps]
    assert day_nums == [1, 2, 3, 4, 5]
    # All should reference field "f1"
    assert all(s["field_id"] == "f1" for s in snaps)


def test_water_stress_is_transpiration_based(client) -> None:
    """water_stress reflects transpiration supply/demand, not θ/FC proxy."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=30&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    patch = data["patches"]["f1"][0]
    ws = patch["water_stress"]
    theta = patch["soil_theta_surface"]
    # Water stress should be between 0 and 1
    assert 0.0 <= ws <= 1.0, f"water_stress {ws} out of range"
    # If theta is well above 0, stress should not be exactly theta/FC
    # (the old proxy). The transpiration-based value has different behavior.
    if theta > 0.05:
        fc = 0.12  # approximate loam field capacity
        proxy = min(theta / fc, 1.0)
        # They should differ because real stress has threshold behavior
        # (stress only kicks in below wilting point, not linearly with theta)
        assert (
            ws != pytest.approx(proxy, abs=0.01) or ws >= 0.95
        ), f"water_stress {ws} ≈ θ/FC proxy {proxy} — should use transpiration"


def test_execute_irrigate_action(client) -> None:
    """POST /action executes irrigation, deducts credits."""
    game_id = _create_game(client)
    # Step 1 day first to init weather
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "irrigate", "params": {"amount_mm": 20}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "executed"
    assert data["action"] == "irrigate"
    assert data["cost_credits"] > 0
    assert data["balance_credits"] < 10000


def test_execute_fertilize_action(client) -> None:
    """POST /action executes fertilization."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={
            "field_id": "f1",
            "action": "fertilize",
            "params": {"type": "urea", "amount_kg_ha": 50},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "executed"


def test_insufficient_credits_rejected(client) -> None:
    """Action rejected when credits insufficient."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    # Try irrigation with enormous amount
    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "irrigate", "params": {"amount_mm": 100000}},
    )
    assert resp.status_code == 400


def test_get_forecast(client) -> None:
    """GET /forecast returns 5-day weather peek."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    resp = client.get(f"/api/v1/games/{game_id}/forecast?seed=42")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_day"] == 1
    assert len(data["forecast"]) == 5
    for day in data["forecast"]:
        assert "tmin_c" in day
        assert "rain_mm" in day


def test_start_season_still_works(client) -> None:
    """Backward compat: /start-season runs all days at once."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/start-season?days=50&seed=42")
    assert resp.status_code == 200
    assert resp.json()["total_days"] == 50


# ---------------------------------------------------------------------------
# AC (#116): harvest report
# ---------------------------------------------------------------------------
def test_harvest_report_after_season(client) -> None:
    """GET /report returns yield, GYGA grade, P&L after completed season."""
    game_id = _create_game(client)
    # Run a season and do an action for cost tracking
    client.post(f"/api/v1/games/{game_id}/start-season?days=100&seed=42")

    resp = client.get(f"/api/v1/games/{game_id}/report")
    assert resp.status_code == 200
    data = resp.json()

    # Structure
    assert "patches" in data
    assert "f1" in data["patches"]
    patch = data["patches"]["f1"][0]
    assert "grain_t_ha" in patch
    assert "gyga_potential_t_ha" in patch
    assert "yield_ratio" in patch
    assert "grade" in patch
    assert patch["grade"] in ("A", "B", "C", "D", "F")
    assert patch["grain_t_ha"] >= 0

    # P&L
    assert "revenue_credits" in data
    assert "total_cost_credits" in data
    assert "profit_credits" in data
    assert "balance_before" in data
    assert "balance_after" in data
    assert "balance_delta" in data

    # Dates
    assert "start_date" in data
    assert "end_date" in data
    assert data["total_days"] == 100


def test_harvest_report_before_season_fails(client) -> None:
    """GET /report before running a season returns 400."""
    game_id = _create_game(client)
    resp = client.get(f"/api/v1/games/{game_id}/report")
    assert resp.status_code == 400


def test_harvest_report_after_stepping_to_maturity(client) -> None:
    """GET /report works after day-by-day stepping (not just /start-season)."""
    game_id = _create_game(client)
    # Step enough days for crop to mature (or exhaust weather)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=200&seed=42")
    assert resp.status_code == 200
    assert resp.json()["season_complete"] is True

    resp = client.get(f"/api/v1/games/{game_id}/report")
    assert resp.status_code == 200
    data = resp.json()
    assert "patches" in data
    assert data["total_days"] == 200


def test_two_season_economics_roundtrip(client) -> None:
    """Full game loop: season 1 with costs → report → season 2 → report.

    Verifies that ledger resets between seasons, balance_before/after are
    correct, and a zero-yield second season shows zero revenue.
    """
    game_id = _create_game(client)

    # --- Season 1: step, take an action, complete, get report ---
    client.post(f"/api/v1/games/{game_id}/step?days=10&seed=42")
    client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "irrigate", "params": {"amount_mm": 20}},
    )
    # Fast-forward rest of season
    client.post(f"/api/v1/games/{game_id}/step?days=190&seed=42")

    r1 = client.get(f"/api/v1/games/{game_id}/report").json()
    assert r1["total_cost_credits"] > 0, "Season 1 should have costs from irrigation"
    assert r1["revenue_credits"] > 0, "Season 1 should have harvest revenue"
    assert r1["balance_after"] > r1["balance_before"], "Profit should increase balance"
    s1_balance_after = r1["balance_after"]

    # Calling report again should NOT change the balance (idempotency)
    r1_again = client.get(f"/api/v1/games/{game_id}/report").json()
    assert (
        r1_again["balance_after"] == s1_balance_after
    ), "Repeated /report must be idempotent"

    # --- Season 2: no actions, fast-forward, get report ---
    client.post(f"/api/v1/games/{game_id}/step?days=200&seed=42")

    r2 = client.get(f"/api/v1/games/{game_id}/report").json()
    assert r2["season_number"] > r1["season_number"], "Season number should increment"
    assert r2["total_cost_credits"] == 0, "Season 2 has no actions = no costs"
    assert r2["balance_before"] == s1_balance_after, (
        f"Season 2 balance_before ({r2['balance_before']}) should equal "
        f"season 1 balance_after ({s1_balance_after})"
    )


# ---------------------------------------------------------------------------
# AC (#140): plant action changes crop and deducts seed cost
# ---------------------------------------------------------------------------
def test_plant_action_changes_crop(client) -> None:
    """Plant action with crop_key resets crop and deducts seed cost."""
    game_id = _create_game(client)
    # Step 1 day to init weather
    client.post(f"/api/v1/games/{game_id}/step?seed=42")

    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={
            "field_id": "f1",
            "action": "plant",
            "params": {"crop_key": "spring_wheat", "patch_idx": 0},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "executed"
    assert data["action"] == "plant"
    assert data["cost_credits"] > 0
    # Seed cost for wheat should be 150 (from prices.yaml)
    assert data["balance_credits"] < 10000

    # Step to see the crop is now wheat
    resp = client.post(f"/api/v1/games/{game_id}/step?days=10")
    assert resp.status_code == 200
    patches = resp.json()["patches"]["f1"]
    # Patch 0 should now be spring_wheat
    assert patches[0]["crop_key"] == "spring_wheat"
