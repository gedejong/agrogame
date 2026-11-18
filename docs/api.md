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
  - tests/test_api_multifield.py
related_adrs: [ADR-002, ADR-003, ADR-005, ADR-017]
---

# API

FastAPI REST API for AgroGame. Powers the Godot frontend (ADR-005) and any
external automation. In-memory game sessions are keyed by `game_id`.

## Endpoints (selected)

- `POST /api/v1/games` — create a game session from
  `{"fields": [{"field_id", "patches": [...]}], "starting_credits"}`. The body
  is rejected with **422**, and no session is created, when (#547, #552):
  - `fields` is empty (a game needs at least one field);
  - two fields share a `field_id` (the detail names it);
  - a field has an empty `patches` list (the detail names the field);
  - a patch's `climate_key` is not a climate preset (the detail names the
    field, the patch index and the valid keys, currently `kenya_highlands`,
    `netherlands_temperate` and `sahel_arid`);
  - a patch's `crop_key` is not a crop preset, or its `soil_profile_key` is
    not a soil preset (the detail names the field, the patch index and the
    valid keys). An empty `crop_key` is a bare, fallow patch (#542) and is
    accepted;
  - a patch's `area_fraction` lies outside (0, 1] (the detail names the field,
    the patch index and the value), even when the field still sums to 1, so a
    1.5 / -0.5 split or a zero-area patch is rejected;
  - a field's patch `area_fraction`s do not sum to 1.0 within ±0.01, so the
    sum must lie in [0.99, 1.01] (the detail names the field, the sum and the
    tolerance). This is the bound `FieldManager` enforces
    (`AREA_FRACTION_SUM_TOLERANCE`), so fractions rounded to three places
    (3 × 0.333 = 0.999) are accepted;
  - the patches carry more than one distinct `climate_key` (the detail lists
    them). Weather is farm-level, so a game has one climate (ADR-002).

  A duplicate `field_id`, an empty `patches` list, an unknown climate, crop or
  soil key and an off-sum area split used to fail with a 500. An empty
  `fields` list used to create a session whose `/forecast` then failed with a
  500, and an out-of-range patch area used to be accepted whenever the field
  summed to 1. A second climate used to be accepted and then ignored, because
  weather follows the first patch's climate.
- `POST /api/v1/games/{game_id}/start-season` — set up a season (crop and
  ledger reset from season 2 on, seeded weather) **without stepping**; see below
- `POST /api/v1/games/{game_id}/step` — advance N days, returning daily snapshots
  and in-season alerts; `stop_on_pause=true` stops on an interrupting alert
- `POST /api/v1/games/{game_id}/action` — apply a management action (plant,
  irrigate, fertilize, harvest, …). `plant` and `harvest` take an optional
  `patch_idx` (default `-1`: every patch). An index at or past the field's
  patch count returns **400** and records no cost (#516); it used to return
  200, and `plant` charged seed while planting nothing. `plant` charges seed
  per ha × each targeted patch's `area_fraction`, rounded per patch, exactly
  as the creation-time seed charge does (#525): on the default field one patch
  of maize costs 67, all three 201.
- `POST /api/v1/games/{game_id}/action/preview` — estimate an action's credit
  cost and affordability without executing it (same cost source as `/action`).
  `patch_idx` is validated as on `/action`, with the same 422 and 400 (#525)
- `GET /api/v1/games/{game_id}` — current session state, including `fields`
  (#516): each `field_id` maps to its patches in order, each
  `{patch_idx, soil_profile_key, crop_key, climate_key, area_fraction}` with the
  patch's current config (`crop_key` is `""` after a per-patch harvest).
  `fields` lists every field in creation order, and the client lays out every
  field from it. (Until #472's client children land, the Godot farm view still
  renders only `fields.field_1`.) `GET /status` carries the same member. An
  unknown `game_id` is a 404.
- `GET /api/v1/games/{game_id}/forecast?field_id=<id>` — short-range forecast:
  weather plus a projected water-stress (FAO-56 Ks) and mineral-N trajectory
  for decision support, anchored on patch 0 of `field_id` (#547). Without
  `field_id` it projects the first field, exactly as before. An unknown
  `field_id` is a 404. The weather part is the same for every field.
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

## In-season alerts (#470, ADR-017)

Every `/step` response lists the alerts raised on the days it stepped:

```json
{"pause_events": [{"day": 6, "field_id": "field_1", "reason": "drought",
  "message": "Drought: water stress Ks 0.33 below 0.40", "interrupt": true}],
 "days_stepped": 6, "days_remaining": 194, "stopped_on_pause": true}
```

`reason` is `drought`, `nutrient_deficiency` or `frost_warning`. Frost is a
notice (`interrupt: false`) and never stops a step. By default `/step` steps
all N days. With `stop_on_pause=true` it stops after the first day on which an
interrupting alert fires, and `days_remaining` is the part of the request left
unstepped, so a client resumes with `/step?days=<days_remaining>`. Stopping and
resuming gives the same simulation as one uninterrupted call. `GET /status`
returns this season's alerts, and `season_result.pause_count` counts the
interrupting ones.

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
