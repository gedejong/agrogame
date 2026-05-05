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
- `POST /api/v1/games/{game_id}/start-season` — run a full season in one call
- `POST /api/v1/games/{game_id}/step` — advance N days, returning daily snapshots
- `POST /api/v1/games/{game_id}/action` — apply a management action (plant,
  irrigate, fertilize, harvest, …)
- `GET /api/v1/games/{game_id}` — current session state
- `GET /api/v1/games/{game_id}/forecast` — short-range weather forecast
- `GET /api/v1/games/{game_id}/report` — end-of-season harvest report

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
