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


def test_step_events_contain_water_infiltrated(client) -> None:
    """Rainy day step should emit WaterInfiltrated event."""
    game_id = _create_game(client)
    # Step 10 days to get past dry days; seed 42 has rain
    resp = client.post(f"/api/v1/games/{game_id}/step?days=10&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    # Check daily_snapshots for WaterInfiltrated events
    all_events = []
    for snap in data["daily_snapshots"]:
        all_events.extend(snap.get("events", []))
    water_events = [e for e in all_events if e["event_type"] == "WaterInfiltrated"]
    assert len(water_events) > 0, "Should have WaterInfiltrated events over 10 days"
    # Verify event structure
    evt = water_events[0]
    assert "layer_indices" in evt["data"]
    assert "amounts_mm" in evt["data"]


def test_step_events_contain_transpiration(client) -> None:
    """Active crop step should emit TranspirationByLayer event."""
    game_id = _create_game(client)
    # Step enough days for crop to grow and transpire
    resp = client.post(f"/api/v1/games/{game_id}/step?days=30&seed=42")
    assert resp.status_code == 200
    data = resp.json()
    all_events = []
    for snap in data["daily_snapshots"]:
        all_events.extend(snap.get("events", []))
    transp = [e for e in all_events if e["event_type"] == "TranspirationByLayer"]
    assert len(transp) > 0, "Should have TranspirationByLayer with active crop"
    evt = transp[0]
    assert "total_mm" in evt["data"]
    assert "amounts_mm" in evt["data"]


def test_step_events_in_patch_response(client) -> None:
    """PatchDayResponse should include events from the final day."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?seed=42")
    assert resp.status_code == 200
    data = resp.json()
    patch = data["patches"]["f1"][0]
    assert "events" in patch
    assert isinstance(patch["events"], list)
    # Should have at least some events (DayTick triggers water/nutrient cycles)
    assert len(patch["events"]) > 0


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


def test_harvest_action_clears_crop_and_settles(client) -> None:
    """Harvest action (#316) clears the crop and returns yield + P&L mid-season.

    Regression: previously `execute_action` had no `harvest` branch, so a
    harvest POST only charged 50 credits and left the crop standing.
    """
    game_id = _create_game(client)
    # Grow the crop for a while so there is grain to settle.
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "executed"
    assert data["action"] == "harvest"
    assert data["cost_credits"] == 50, "Harvest charges the labor cost"
    # Settlement fields returned inline (so the frontend can surface P&L).
    assert data["grain_g_m2"] > 0.0, "Harvested grain reported"
    assert data["revenue_credits"] > 0, "Harvest produced revenue"
    # profit = revenue - season costs (which include the 50-credit harvest labor)
    assert data["profit_credits"] == data["revenue_credits"] - 50

    # Crop is cleared: a subsequent /step reports a bare patch.
    resp = client.post(f"/api/v1/games/{game_id}/step?days=1")
    assert resp.status_code == 200
    patches = resp.json()["patches"]["f1"]
    assert patches[0]["crop_key"] == "", "Crop cleared after harvest"


def test_harvest_action_enables_report_mid_season(client) -> None:
    """After a harvest action, GET /report succeeds mid-season (#316).

    Regression: /report returned 400 unless a full season completed, because
    `turn_manager.result` was only set by `_finalize_season`.
    """
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    # Report is unavailable before harvesting mid-season.
    pre = client.get(f"/api/v1/games/{game_id}/report")
    assert pre.status_code == 400

    harvest = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert harvest.status_code == 200

    report = client.get(f"/api/v1/games/{game_id}/report")
    assert report.status_code == 200
    rj = report.json()
    # Report P&L is consistent with the harvest action's settlement.
    assert rj["revenue_credits"] == harvest.json()["revenue_credits"]
    assert rj["revenue_credits"] > 0


def test_double_harvest_is_noop(client) -> None:
    """A second harvest on a bare patch is a no-op: no charge, no clobber (#341).

    Regression: `execute_action` had no guard, so re-harvesting an
    already-harvested patch charged another 50 credits (revenue 0) and
    overwrote `turn_manager.result` with a zero-grain SeasonResult.
    """
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    first = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "executed"
    balance_after_first = first.json()["balance_credits"]

    report_after_first = client.get(f"/api/v1/games/{game_id}/report").json()

    # Second harvest: the patch is now bare, so it must be a no-op.
    second = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert second.status_code == 200
    sj = second.json()
    assert sj["status"] == "no-op", "Re-harvest of a bare patch is a no-op"
    assert sj["cost_credits"] == 0, "No labor charged for a no-op harvest"
    assert sj["revenue_credits"] == 0
    assert sj["balance_credits"] == balance_after_first, "Balance unchanged"

    # turn_manager.result / report is not clobbered by the no-op.
    report_after_second = client.get(f"/api/v1/games/{game_id}/report").json()
    assert (
        report_after_second["revenue_credits"] == report_after_first["revenue_credits"]
    )
    # The per-patch yield captured at the real harvest also survives the no-op.
    assert (
        report_after_second["patches"]["f1"][0]["grain_t_ha"]
        == report_after_first["patches"]["f1"][0]["grain_t_ha"]
    )


def test_report_preserves_per_patch_yield_after_harvest(client) -> None:
    """/report keeps per-patch grain_t_ha and crop after harvest clears the crop (#341).

    Regression: clearing the crop zeroed `grain_biomass_g_m2`, so the per-patch
    `grain_t_ha` in /report read 0.0 even though grain was harvested.
    """
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    harvest = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert harvest.status_code == 200
    grain_g_m2 = harvest.json()["grain_g_m2"]
    assert grain_g_m2 > 0.0

    report = client.get(f"/api/v1/games/{game_id}/report")
    assert report.status_code == 200
    patch = report.json()["patches"]["f1"][0]
    # Per-patch yield reflects the harvested grain, not the cleared 0.0.
    assert patch["grain_t_ha"] > 0.0, "Per-patch yield preserved after harvest"
    # /report serializes grain_t_ha as round(grain_g_m2 / 100.0, 2), so compare
    # like-for-like at 2-dp resolution. abs=0.01 (one hundredths step) absorbs the
    # action response's own 1-dp grain rounding landing on the far side of a
    # hundredths boundary, while still asserting the yield is preserved to 2 dp.
    assert patch["grain_t_ha"] == pytest.approx(round(grain_g_m2 / 100.0, 2), abs=0.01)
    # Crop identity survives the clear, so the GYGA lookup resolves to maize's
    # water-limited potential (11.0) rather than the 10.0 empty-crop default.
    assert patch["crop_key"] == "maize"
    assert patch["gyga_potential_t_ha"] == 11.0


def test_replant_resets_harvested_yield_in_report(client) -> None:
    """Replanting after harvest clears the stale per-patch yield in /report (#341)."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")
    client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )

    # Replant a fresh crop; the just-harvested yield must not carry over.
    plant = client.post(
        f"/api/v1/games/{game_id}/action",
        json={
            "field_id": "f1",
            "action": "plant",
            "params": {"crop_key": "maize", "patch_idx": 0},
        },
    )
    assert plant.status_code == 200

    report = client.get(f"/api/v1/games/{game_id}/report")
    assert report.status_code == 200
    patch = report.json()["patches"]["f1"][0]
    # Fresh crop, no grain yet — report reads live state, not the prior harvest.
    assert patch["crop_key"] == "maize"
    assert patch["grain_t_ha"] == 0.0


# ---------------------------------------------------------------------------
# AC (#359): harvest honors patch_idx, resets _current_crop, mid-season P&L
# ---------------------------------------------------------------------------
def _session(game_id: str):
    """Grab the in-memory GameSession for white-box assertions."""
    from agrogame.api.state import games

    return games[game_id]


def test_harvest_targets_requested_patch_only(client) -> None:
    """Harvesting patch_idx=1 clears only that patch; others stay standing (#359).

    Regression: `_harvest_action` harvested every patch regardless of the
    requested `patch_idx`, so a multi-patch field lost all its standing crops.
    """
    game_id = _create_multi_patch_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 1}},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "executed"

    step = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    patches = step.json()["patches"]["f1"]
    # Only patch 1 is cleared; patches 0 and 2 keep their standing maize.
    assert patches[0]["crop_key"] == "maize", "Patch 0 untouched"
    assert patches[1]["crop_key"] == "", "Patch 1 harvested and cleared"
    assert patches[2]["crop_key"] == "maize", "Patch 2 untouched"


def test_harvest_targets_each_patch_across_two_cycles(client) -> None:
    """Sequentially harvesting patch 0 then patch 2 clears exactly those (#359)."""
    game_id = _create_multi_patch_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    # Cycle 1: harvest patch 0.
    r0 = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert r0.json()["status"] == "executed"
    step1 = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    p1 = step1.json()["patches"]["f1"]
    assert p1[0]["crop_key"] == ""
    assert p1[1]["crop_key"] == "maize"
    assert p1[2]["crop_key"] == "maize"

    # Cycle 2: harvest patch 2 — patch 1 still stands, patch 0 stays bare.
    r2 = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 2}},
    )
    assert r2.json()["status"] == "executed"
    step2 = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    p2 = step2.json()["patches"]["f1"]
    assert p2[0]["crop_key"] == ""
    assert p2[1]["crop_key"] == "maize", "Patch 1 still standing after two harvests"
    assert p2[2]["crop_key"] == ""


def test_harvest_on_bare_target_is_noop_even_if_other_patches_stand(client) -> None:
    """Harvesting an already-bare patch is a no-op though other patches stand (#359).

    The no-op guard must be scoped to the requested patch, not "any patch has a
    crop" — otherwise re-harvesting patch 0 would fire on patch 1's crop.
    """
    game_id = _create_multi_patch_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    first = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert first.json()["status"] == "executed"

    # Patch 0 is now bare; re-harvesting it must no-op even though patches 1/2
    # still carry crops.
    second = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    sj = second.json()
    assert sj["status"] == "no-op"
    assert sj["cost_credits"] == 0


def test_harvest_out_of_range_patch_idx_is_noop(client) -> None:
    """Out-of-range patch_idx harvests nothing (no-op), never the wrong patch (#359)."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 5}},
    )
    assert resp.json()["status"] == "no-op"
    # The still-standing crop is untouched.
    step = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    assert step.json()["patches"]["f1"][0]["crop_key"] == "maize"


def test_harvest_resets_current_crop(client) -> None:
    """Harvest clears orch._current_crop so no stale crop reference persists (#359)."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    sess = _session(game_id)
    orch = sess.field_manager.fields["f1"].patches[0].orch
    assert orch._current_crop is not None, "Crop present before harvest"

    client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    assert orch._current_crop is None, "Harvest resets _current_crop to None"


def test_harvest_resets_current_crop_per_targeted_patch(client) -> None:
    """Only the targeted patch's _current_crop is reset; others keep theirs (#359)."""
    game_id = _create_multi_patch_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    sess = _session(game_id)
    patches = sess.field_manager.fields["f1"].patches
    assert all(p.orch._current_crop is not None for p in patches)

    client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 1}},
    )
    assert patches[0].orch._current_crop is not None, "Patch 0 crop reference kept"
    assert patches[1].orch._current_crop is None, "Patch 1 crop reference reset"
    assert patches[2].orch._current_crop is not None, "Patch 2 crop reference kept"


def test_harvest_single_patch_revenue_is_area_scaled(client) -> None:
    """A single patch settles only its area share, never out-earning the field (#359).

    Regression: `_harvest_action` settled a single patch's grain *density* with
    the default ``area_ha=1.0``, so one patch was credited as a whole hectare and
    could out-earn a full-field harvest. Settlement now scales by the targeted
    patches' ``area_fraction`` sum.
    """
    # Full-field harvest (patch_idx defaults to -1 → whole 1 ha field).
    field_game = _create_multi_patch_game(client)
    client.post(f"/api/v1/games/{field_game}/step?days=110&seed=42")
    full = client.post(
        f"/api/v1/games/{field_game}/action",
        json={"field_id": "f1", "action": "harvest", "params": {}},
    ).json()
    assert full["status"] == "executed"
    full_revenue = full["revenue_credits"]
    assert full_revenue > 0

    # Single-patch harvest on an identical game/seed.
    patch_game = _create_multi_patch_game(client)
    client.post(f"/api/v1/games/{patch_game}/step?days=110&seed=42")
    single = client.post(
        f"/api/v1/games/{patch_game}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 1}},
    ).json()
    assert single["status"] == "executed"
    single_revenue = single["revenue_credits"]

    assert single_revenue > 0, "A harvested patch still earns its area share"
    assert single_revenue < full_revenue, (
        "One patch (~1/3 ha) must not out-earn the whole field — "
        f"single={single_revenue}, full={full_revenue}"
    )


def test_harvest_bad_patch_idx_returns_422(client) -> None:
    """A malformed patch_idx yields a clean 422, not an unhandled 500 (#359 review).

    Regression: `int(req.params.get("patch_idx", -1))` raised ValueError/TypeError
    on non-numeric input, surfacing as a 500. The API boundary now validates it.
    """
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    for bad in ("not-an-int", None, [1, 2]):
        resp = client.post(
            f"/api/v1/games/{game_id}/action",
            json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": bad}},
        )
        assert resp.status_code == 422, f"patch_idx={bad!r} should be a 422"


def test_report_balance_delta_mid_season_reflects_pnl(client) -> None:
    """balance_delta equals the running P&L after a mid-season harvest (#359).

    Regression: /report computed balance_delta as (balance_after -
    balance_before) around its own settlement. A mid-season harvest action had
    already settled the season, so that difference was 0 even though the sale
    changed the balance.
    """
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?days=110&seed=42")

    harvest = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "harvest", "params": {"patch_idx": 0}},
    )
    hj = harvest.json()
    assert hj["profit_credits"] != 0

    report = client.get(f"/api/v1/games/{game_id}/report").json()
    # Running P&L is revenue − season costs, matching the harvest action's profit.
    assert report["balance_delta"] != 0, "Mid-season balance_delta must not read 0"
    assert report["balance_delta"] == hj["profit_credits"]
    assert report["balance_delta"] == (
        report["revenue_credits"] - report["total_cost_credits"]
    )


def test_report_balance_delta_full_season_equals_profit(client) -> None:
    """When /report settles the season itself, balance_delta is still the P&L (#359)."""
    game_id = _create_game(client)
    # Full season settled by /report (no mid-season harvest action).
    client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "irrigate", "params": {"amount_mm": 20}},
    )
    client.post(f"/api/v1/games/{game_id}/step?days=200&seed=42")

    report = client.get(f"/api/v1/games/{game_id}/report").json()
    assert report["balance_delta"] == report["profit_credits"]
    assert report["balance_delta"] == (
        report["revenue_credits"] - report["total_cost_credits"]
    )


def test_step_response_includes_redox_state(client) -> None:
    """Step response should include redox_eh and dominant_acceptor (#235).

    After #284 wired gas diffusion into the orchestrator, Eh is driven
    by per-layer O₂ rather than the WFPS sigmoid. With uniform per-layer
    SOM respiration the diffusion solver pushes deep layers toward
    anaerobic faster than the WFPS proxy did, so this test checks
    topsoil aerobic only — depth-stratified respiration is tracked
    separately as a SOM calibration follow-up.
    """
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
    assert resp.status_code == 200
    patches = resp.json()["patches"]["f1"]
    soil = patches[0]["soil_state"]
    # redox_eh should be a list of floats (one per layer)
    assert "redox_eh" in soil
    assert isinstance(soil["redox_eh"], list)
    assert len(soil["redox_eh"]) > 0
    # Topsoil should be aerobic after 5 days of light rain (well-drained loam).
    assert soil["redox_eh"][0] > 0
    # Deeper layers may go reductive, but should not be *catastrophically*
    # over-reduced (e.g. Eh < -300 mV is methanogenic-bog territory and not
    # plausible for a well-drained loam after only 5 days). Floor protects
    # the test from masking a future regression that drives all layers
    # severely anaerobic; -300 mV is a safe non-tight bound (CH4 onset is
    # roughly -200 mV; Patrick & Reddy 1978).
    assert min(soil["redox_eh"][1:]) > -300
    # dominant_acceptor should be a list of strings
    assert "dominant_acceptor" in soil
    assert isinstance(soil["dominant_acceptor"], list)
    assert len(soil["dominant_acceptor"]) > 0
    assert soil["dominant_acceptor"][0] in ("O2", "NO3", "Fe3+", "CH4")


def test_step_response_includes_micronutrients(client) -> None:
    """Step response should include Fe, Zn, Mn availability (#237)."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
    assert resp.status_code == 200
    patches = resp.json()["patches"]["f1"]
    soil = patches[0]["soil_state"]
    for elem in ("fe_available", "zn_available", "mn_available"):
        assert elem in soil, f"{elem} missing from soil_state"
        assert isinstance(soil[elem], list)
        assert len(soil[elem]) > 0
        assert all(v >= 0 for v in soil[elem])


def test_step_response_includes_aggregation(client) -> None:
    """Step response should include aggregate fractions and MWD (#248)."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
    assert resp.status_code == 200
    patches = resp.json()["patches"]["f1"]
    soil = patches[0]["soil_state"]
    for key in ("agg_macro", "agg_meso", "agg_micro", "agg_mwd"):
        assert key in soil, f"{key} missing from soil_state"
        assert isinstance(soil[key], list)
        assert len(soil[key]) > 0
    # Fractions should sum to ~1.0 per layer
    for i in range(len(soil["agg_macro"])):
        total = soil["agg_macro"][i] + soil["agg_meso"][i] + soil["agg_micro"][i]
        assert abs(total - 1.0) < 0.01, f"Layer {i} fractions sum to {total}"
    # MWD should be positive
    assert all(m > 0 for m in soil["agg_mwd"])
    # DailySnapshots should include agg_mwd_surface
    snaps = resp.json().get("daily_snapshots", [])
    if snaps:
        assert "agg_mwd_surface" in snaps[0]
        assert snaps[0]["agg_mwd_surface"] > 0


def test_tillage_reduces_macro(client) -> None:
    """Tillage action via API should reduce macroaggregate fraction (#248)."""
    game_id = _create_game(client)
    # Step a few days to establish baseline
    resp = client.post(f"/api/v1/games/{game_id}/step?days=3&seed=42")
    assert resp.status_code == 200
    soil_before = resp.json()["patches"]["f1"][0]["soil_state"]
    macro_before = soil_before["agg_macro"][0]
    # Apply intensive tillage
    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={
            "field_id": "f1",
            "action": "tillage",
            "params": {"intensity": 1.0},
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "tillage"
    # Step to see the soil state after tillage
    resp = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    assert resp.status_code == 200
    soil_after = resp.json()["patches"]["f1"][0]["soil_state"]
    macro_after = soil_after["agg_macro"][0]
    assert (
        macro_after < macro_before
    ), f"Tillage should reduce macro: {macro_before} → {macro_after}"
    # Mass conservation: fractions must still sum to ~1.0
    for i in range(len(soil_after["agg_macro"])):
        total = (
            soil_after["agg_macro"][i]
            + soil_after["agg_meso"][i]
            + soil_after["agg_micro"][i]
        )
        assert abs(total - 1.0) < 0.01, f"Layer {i} fractions sum to {total}"


# ---------------------------------------------------------------------------
# AC (#318): action cost preview + soil/crop forecast
# ---------------------------------------------------------------------------
def test_preview_action_returns_cost(client) -> None:
    """POST /action/preview returns cost + affordability without executing."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    balance_before = client.get(f"/api/v1/games/{game_id}/status").json()[
        "balance_credits"
    ]
    resp = client.post(
        f"/api/v1/games/{game_id}/action/preview",
        json={"field_id": "f1", "action": "irrigate", "params": {"amount_mm": 20}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "irrigate"
    assert data["cost_credits"] > 0
    assert data["affordable"] is True
    # Preview must NOT deduct credits.
    balance_after = client.get(f"/api/v1/games/{game_id}/status").json()[
        "balance_credits"
    ]
    assert balance_after == balance_before


def test_preview_action_unaffordable_flag(client) -> None:
    """Preview flags actions that exceed the balance as not affordable."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    resp = client.post(
        f"/api/v1/games/{game_id}/action/preview",
        json={"field_id": "f1", "action": "irrigate", "params": {"amount_mm": 100000}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["affordable"] is False
    assert data["cost_credits"] > data["balance_credits"]


def test_preview_action_unknown_action_rejected(client) -> None:
    game_id = _create_game(client)
    resp = client.post(
        f"/api/v1/games/{game_id}/action/preview",
        json={"field_id": "f1", "action": "nonsense", "params": {}},
    )
    assert resp.status_code == 400


def test_preview_action_unknown_field_rejected(client) -> None:
    game_id = _create_game(client)
    resp = client.post(
        f"/api/v1/games/{game_id}/action/preview",
        json={"field_id": "nope", "action": "irrigate", "params": {}},
    )
    assert resp.status_code == 404


def test_preview_cost_matches_executed_cost(client) -> None:
    """Contract test (AC4): preview cost == executed /action cost, per action."""
    cases = [
        ("irrigate", {"amount_mm": 15}),
        ("fertilize", {"type": "urea", "amount_kg_ha": 40}),
        ("tillage", {"intensity": 0.5}),
        ("plant", {"crop_key": "maize", "patch_idx": 0}),
        ("harvest", {}),
    ]
    for action, params in cases:
        game_id = _create_game(client)
        client.post(f"/api/v1/games/{game_id}/step?seed=42")
        preview = client.post(
            f"/api/v1/games/{game_id}/action/preview",
            json={"field_id": "f1", "action": action, "params": params},
        ).json()
        executed = client.post(
            f"/api/v1/games/{game_id}/action",
            json={"field_id": "f1", "action": action, "params": params},
        ).json()
        assert (
            preview["cost_credits"] == executed["cost_credits"]
        ), f"{action}: preview {preview} != executed {executed}"


def test_forecast_includes_soil_projection(client) -> None:
    """GET /forecast projects water-stress and mineral-N, not just weather."""
    game_id = _create_game(client)
    client.post(f"/api/v1/games/{game_id}/step?seed=42")
    resp = client.get(f"/api/v1/games/{game_id}/forecast?seed=42")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["forecast"]) == 5
    for day in data["forecast"]:
        assert "water_stress" in day
        assert "mineral_n_kg_ha" in day
        assert 0.0 <= day["water_stress"] <= 1.0
        assert day["mineral_n_kg_ha"] >= 0.0


def test_forecast_mineral_n_trend_matches_engine_sign(client) -> None:
    """GET /forecast mineral-N trend agrees in sign with real engine steps (#353).

    Early-season loam maize accumulates root-zone mineral N (SOM net
    mineralisation dominates the tiny uptake). The projection must trend the
    same way, not opposite (the sink-only bug). We compare a 5-day forecast
    anchored on the established state against 5 real no-action engine steps.
    """
    game_id = _create_game(client)

    def _profile_mineral_n(step_resp: dict) -> float:
        soil = step_resp["patches"]["f1"][0]["soil_state"]
        return sum(soil["n_no3"]) + sum(soil["n_nh4"])  # whole-profile g/m²

    # Establish ~20 days; the final step response gives the anchor soil state.
    before = _profile_mineral_n(
        client.post(f"/api/v1/games/{game_id}/step?days=20&seed=42").json()
    )

    fc = client.get(f"/api/v1/games/{game_id}/forecast?days=5&seed=42").json()[
        "forecast"
    ]
    forecast_n = [d["mineral_n_kg_ha"] for d in fc]
    assert forecast_n[-1] > forecast_n[0], "forecast N should rise, not fall"

    # Step 5 real no-action days on the same weather and re-read profile N.
    after = _profile_mineral_n(
        client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42").json()
    )

    engine_delta = after - before
    forecast_delta = forecast_n[-1] - forecast_n[0]
    assert engine_delta > 0.0, "engine profile mineral N should rise here"
    assert (forecast_delta > 0) == (engine_delta > 0), "sign disagreement (#353)"


# ---------------------------------------------------------------------------
# Soil-response expansion — biology (#317), pore network (#274),
# dynamic soil properties (#253)
# ---------------------------------------------------------------------------
def test_step_response_includes_microbial_biology(client) -> None:
    """Soil state exposes microbial N + fungal fraction, root/stem biomass (#317)."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=40&seed=42")
    assert resp.status_code == 200
    soil = resp.json()["patches"]["f1"][0]["soil_state"]

    # Per-layer microbial N (kg/ha) and fungal fraction (0..1)
    for key in ("microbe_n", "fungal_fraction"):
        assert key in soil, f"{key} missing from soil_state"
        assert isinstance(soil[key], list)
        assert len(soil[key]) > 0
    assert all(v >= 0.0 for v in soil["microbe_n"])
    assert all(0.0 <= f <= 1.0 for f in soil["fungal_fraction"])
    # microbe_n and microbe_c should have matching per-layer length
    assert len(soil["microbe_n"]) == len(soil["microbe_c"])

    # Root + stem biomass surfaced (#317)
    assert "root_biomass_g_m2" in soil
    assert "root_layer_fractions" in soil
    assert "stem_biomass_g_m2" in soil
    assert soil["root_biomass_g_m2"] >= 0.0
    # A maize crop mid-season should have accumulated some stem biomass.
    assert soil["stem_biomass_g_m2"] > 0.0
    # Root layer fractions are populated once the crop is rooting: non-negative,
    # summing to ~1 across the rooted profile.
    assert soil["root_layer_fractions"]
    assert all(f >= 0.0 for f in soil["root_layer_fractions"])
    assert abs(sum(soil["root_layer_fractions"]) - 1.0) < 0.02


def test_step_response_includes_pore_network(client) -> None:
    """Soil state exposes per-layer pore fractions + connectivity (#274)."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
    assert resp.status_code == 200
    soil = resp.json()["patches"]["f1"][0]["soil_state"]

    for key in (
        "pore_macro_frac",
        "pore_meso_frac",
        "pore_micro_frac",
        "pore_crypto_frac",
        "pore_connectivity",
    ):
        assert key in soil, f"{key} missing from soil_state"
        assert isinstance(soil[key], list)
        assert len(soil[key]) > 0
        assert all(v >= 0.0 for v in soil[key])

    # Connectivity index is bounded 0..1.
    assert all(0.0 <= t <= 1.0 for t in soil["pore_connectivity"])

    # Pore fractions sum to total porosity per layer (Greenland 1977).
    n = len(soil["pore_macro_frac"])
    for i in range(n):
        pore_sum = (
            soil["pore_macro_frac"][i]
            + soil["pore_meso_frac"][i]
            + soil["pore_micro_frac"][i]
            + soil["pore_crypto_frac"][i]
        )
        # Total porosity of arable soils is roughly 0.3–0.6 m³/m³.
        assert 0.2 <= pore_sum <= 0.65, f"Layer {i} pore sum {pore_sum} implausible"

    # Surface macroporosity sparkline field present and plausible.
    snaps = resp.json().get("daily_snapshots", [])
    if snaps:
        assert "pore_macro_frac_surface" in snaps[0]
        assert 0.0 <= snaps[0]["pore_macro_frac_surface"] <= 0.30


def test_step_response_includes_dynamic_soil_properties(client) -> None:
    """Soil state exposes dynamic ksat (mm/day) + porosity per layer (#253)."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=5&seed=42")
    assert resp.status_code == 200
    soil = resp.json()["patches"]["f1"][0]["soil_state"]

    for key in ("ksat_mm_day", "porosity"):
        assert key in soil, f"{key} missing from soil_state"
        assert isinstance(soil[key], list)
        assert len(soil[key]) > 0
    # ksat positive; loam surface ksat is O(10–200 mm/day) but bounded well below.
    assert all(k > 0.0 for k in soil["ksat_mm_day"])
    assert soil["ksat_mm_day"][0] < 5000.0
    # Dynamic porosity clamped to physical bounds by effective_porosity().
    assert all(0.30 <= p <= 0.60 for p in soil["porosity"])

    snaps = resp.json().get("daily_snapshots", [])
    if snaps:
        assert "ksat_surface" in snaps[0]
        assert snaps[0]["ksat_surface"] > 0.0


def test_tillage_lowers_dynamic_ksat(client) -> None:
    """Tillage destroys macroaggregates → dynamic surface ksat drops (#253)."""
    game_id = _create_game(client)
    resp = client.post(f"/api/v1/games/{game_id}/step?days=3&seed=42")
    assert resp.status_code == 200
    ksat_before = resp.json()["patches"]["f1"][0]["soil_state"]["ksat_mm_day"][0]

    resp = client.post(
        f"/api/v1/games/{game_id}/action",
        json={"field_id": "f1", "action": "tillage", "params": {"intensity": 1.0}},
    )
    assert resp.status_code == 200
    resp = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    assert resp.status_code == 200
    ksat_after = resp.json()["patches"]["f1"][0]["soil_state"]["ksat_mm_day"][0]
    assert (
        ksat_after < ksat_before
    ), f"Tillage should lower dynamic ksat: {ksat_before} → {ksat_after}"


def test_bare_soil_has_zero_plant_biomass(client) -> None:
    """Before emergence, root/stem biomass are zero but microbes populated (#317)."""
    game_id = _create_game(client)
    # One day: crop has not emerged yet, so no root/stem biomass.
    resp = client.post(f"/api/v1/games/{game_id}/step?days=1&seed=42")
    assert resp.status_code == 200
    soil = resp.json()["patches"]["f1"][0]["soil_state"]
    assert soil["stem_biomass_g_m2"] == 0.0
    # Microbial fields still populated for bare/unemerged soil.
    assert len(soil["microbe_n"]) > 0
    assert any(v > 0.0 for v in soil["microbe_n"])
