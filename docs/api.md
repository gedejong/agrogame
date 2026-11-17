---
module: agrogame.api
doc_type: module
references:
  - "FastAPI documentation — REST API patterns"
  - "ADR-005 — Frontend architecture (Godot ↔ FastAPI)"
key_classes: []
key_events: []
primary_tests:
  - tests/test_api.py
related_adrs: [ADR-002, ADR-003, ADR-004, ADR-005]
---

# API

FastAPI REST API for AgroGame. Powers the Godot frontend (ADR-005) and any
external automation. In-memory game sessions are keyed by `game_id`.

## Endpoints (selected)

- `POST /api/v1/games` — create a game session
- `POST /api/v1/games/{game_id}/start-season` — set up a season (crop and
  ledger reset from season 2 on, seeded weather) **without stepping**; see below
- `POST /api/v1/games/{game_id}/step` — advance N days, returning daily snapshots
- `POST /api/v1/games/{game_id}/action` — apply a management action (plant,
  irrigate, fertilize, harvest, …). `plant` and `harvest` take an optional
  `patch_idx` (default `-1`: every patch). An index at or past the field's
  patch count returns **400** and records no cost (#516); it used to return
  200, and `plant` charged seed while planting nothing.
- `POST /api/v1/games/{game_id}/action/preview` — estimate an action's credit
  cost and affordability without executing it (same cost source as `/action`)
- `GET /api/v1/games/{game_id}` — current session state, including `fields`
  (#516): each `field_id` maps to its patches in order, each
  `{patch_idx, soil_profile_key, crop_key, climate_key, area_fraction}` with the
  patch's current config (`crop_key` is `""` after a per-patch harvest). The
  Godot farm view lays out its tile bands from `fields.field_1`. `GET /status`
  carries the same member. An unknown `game_id` is a 404.
- `GET /api/v1/games/{game_id}/forecast` — short-range forecast: weather plus a
  projected water-stress (FAO-56 Ks) and mineral-N trajectory for decision support
- `GET /api/v1/games/{game_id}/report` — end-of-season harvest report

## One day loop (#487)

`/step` is the only path that advances simulation days, so per-day behaviour
(snapshots, recorder events, pause detection) exists in one place.
`/start-season` used to run its own embedded 150-day loop; it now only sets the
season up and returns a `SeasonStartedResponse`:

```json
{"season_number": 1, "start_date": "2024-04-01", "season_days": 150, "day_number": 0}
```

A client runs a whole season with `/start-season` followed by
`/step?days=<season_days>`. End-of-season results come from that final `/step`
(`season_complete: true`), `GET /status` (`season_result`) and `/report`.
Driven this way, a season is numerically identical to the old embedded loop.

The `/step` that first reports `season_complete: true` also settles the season
(#518): every standing crop in every field is sold, so that response's
`balance_credits` already includes the revenue. `/report` is a read with no
side effects. Until the next season starts, `harvest` on `/action` and
`/action/preview` returns 400 ("Season settled: start the next season").

## Run

```bash
poetry install -E api
poetry run make serve-api
```

The API binds to `localhost:8000` by default; the Godot client points at
`localhost:8000/api/v1/`.

## Architecture

Routes live in `agrogame/api/routes.py`. Pydantic request/response models
in `agrogame/api/models.py`. Session state held in `agrogame/api/state.py`.
Game logic delegates to `agrogame.game` (economy, turns) and
`agrogame.sim` (orchestrator).
