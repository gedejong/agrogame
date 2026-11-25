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
  and in-season alerts; `stop_on_pause=true` stops on an interrupting alert.
  `som_total_c_g_m2` (on `soil_state`, each patch's day result and `/report`) is
  the whole-profile SOM carbon in g C/m²: the pool arrays are kg C/ha and the
  field is their sum ÷ 10. Before #629 it carried the kg C/ha sum, 10× high.
- `POST /api/v1/games/{game_id}/action` — apply a management action (plant,
  irrigate, fertilize, harvest, …). `plant` and `harvest` take an optional
  `patch_idx` (default `-1`: every patch). An index at or past the field's
  patch count returns **400** and records no cost (#516); it used to return
  200, and `plant` charged seed while planting nothing. `plant` charges seed
  per ha × each targeted patch's `area_fraction`, rounded per patch, exactly
  as the creation-time seed charge does (#525): on the default field one patch
  of maize costs 67, all three 201.
  Every `/action` reply carries `date` (ISO session date after the action,
  additive, #631). A `harvest` reply also carries `settlements`, one entry per
  crop group settled (a full-field harvest is one entry today), and `[]` for
  every other action and for a no-op. Each entry holds `crop_key`, `product`
  (`grain` or `fruit`), `patch_indices`, `area_ha` (ha), `dry_kg_ha` (kg/ha
  dry mass), `dry_matter_fraction` (0 to 1), `sold_kg_ha` (kg/ha fresh),
  `sold_kg` (kg over the area), `quarter` (1 to 4), `base_credits_per_kg`,
  `seasonal_multiplier`, `price_credits_per_kg` (base x multiplier, cr/kg) and
  `revenue_credits` (ledger delta, credits; the reply's `revenue_credits` is
  their sum). The client renders these as the harvest receipt.
- `POST /api/v1/games/{game_id}/action/preview` — estimate an action's credit
  cost and affordability without executing it (same cost source as `/action`).
  `patch_idx` is validated as on `/action`, with the same 422 and 400 (#525)
- `GET /api/v1/games/{game_id}` — current session state, including `fields`
  (#516): each `field_id` maps to its patches in order, each
  `{patch_idx, soil_profile_key, soil_name, crop_key, climate_key,
  area_fraction}` with the patch's current config (`crop_key` is `""` after a per-patch harvest). `soil_name` is the soil
  preset's display name from `data/soils/presets.yaml` (e.g. `Loam - Temperate`),
  which the client shows instead of deriving a label from the key (#629).
  `fields` lists every field in creation order, and the client lays out every
  field from it (#600): fields as row bands of the 6x6 map in this order, each
  field's patches as column bands, and day results, Plant and Harvest mapped by
  (field, patch). Irrigate, Fertilize, Tillage and Lime still name `field_1`
  until the client's active field (#601). `GET /status` carries the same
  member. An unknown `game_id` is a 404.
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

`daily_snapshots[]` also carries `root_depth_cm` (cm, 1 dp), the same value as
`patches[...].root_depth_cm` on that day; 0.0 for a bare patch (#630).
`HeatDamageApplied` and `FrostDamageApplied` events carry `threshold_c` (°C), the
crop's heat or frost threshold, so a client can say what a damage day crossed (#630).

## Crop gauges (#660)

Each `patches[...]` day result carries what the Quick Status card's gauges read:

| Field | Meaning |
|---|---|
| `water_stress` | The **growth water factor**, not Ks: the running mean of daily Ta/Tp over the crop's `stress_memory_days` times the VPD RUE factor; 2 dp. Today's Ks is the last `WaterStressComputed.stress` in `events`, the value the ADR-017 drought alert reads. |
| `growth_vs_potential` | Shoot biomass so far over the biomass of a read-only **potential-production shadow canopy**: the same crop, same light, temperature and VPD factor, with water and nutrients unlimited and no frost, waterlogging or drought-senescence damage (van Ittersum & Rabbinge 1997, *Field Crops Res.* 52:197-208). 0 to 1, 3 dp; `null` on a bare patch and before the potential has any biomass (before emergence). It freezes at maturity as the season's realised share of potential. |
| `root_zone_water_fraction` | Plant-available water over total available water (TAW) in the root zone (FAO-56 Eq. 82), with the root depth floored at the top layer's thickness; 3 dp. Uncapped: above 1 when the profile is wetter than field capacity (peat), 0.0 when TAW is 0. Set on bare patches too. |
| `depletion_fraction_p` | The crop's FAO-56 Table 22 depletion fraction p for no stress (RAW = p · TAW, Eq. 83): maize, sorghum and both wheats 0.55, soybean 0.50, rice 0.20 (Table 22 footnote 4, applied to TAW), grape 0.45 (wine). `null` on a bare patch. Display only: no engine module reads it. |

The shadow canopy is saved with the patch (`potential_canopy_state`, optional in
schema v1); a save without it seeds the potential from the actual canopy. A
crop change starts a fresh one. It changes no simulated quantity.

## Event payloads (#562)

`/step` lists each day's simulation events in `patches[...].events` and
`daily_snapshots[].events`; [API events](api-events.md) is the per-type
reference. Every event `data` value is plain JSON data, and two identical runs
(same game, same seed) return byte-identical `/step` responses:

- A nested record is an object of its fields. `DayTick.drivers`, set on the
  `water` and `et` phases and `null` on the others, is
  `{"rainfall_mm", "irrigation_mm", "evaporation_mm", "rainfall_intensity_mm_hr"}`.
- A date is an ISO string (`"sim_date": "2024-04-01"`), and an enum is its
  value (`StageChanged` stages are `"emerged"`, `"flowering"`, … as in
  `crop_stage`).
- The emit wall-clock `timestamp` is not sent. Simulated time is the
  response's `date`.

`DayTick.drivers` used to go out as Python's
`<agrogame.soil.water.types.DailyDrivers object at 0x…>`, stage changes as
`PhenologyStage.EMERGED`, and every event carried the server's wall-clock
`timestamp`, so no two runs matched byte for byte. The client reads none of
these fields. A payload value with no JSON form is now a server error naming
its type, where it used to be sent as its repr. A unit test discovers every
`BaseEvent` subclass in `agrogame` and serialises one instance of each, so a
new event type with such a field fails in CI rather than during play.

## Simulation errors (#606)

A simulation handler that raises fails the request with **500** and names the
failing handler and event type:

```json
{"detail": "agrogame.atmosphere.et.runtime.ETRuntime._on_day_tick raised AttributeError while handling DayTick",
 "handler": "agrogame.atmosphere.et.runtime.ETRuntime._on_day_tick",
 "event_type": "DayTick"}
```

This is a simulation defect, not a bad request. The server logs it at ERROR
with the traceback, and the body carries no traceback or exception message.
The mapping is app-wide, so `/action`, `/start-season` and `/load` answer
the same way as `/step`. The session is **not rolled back**: its patches may be partly stepped, so the
client should start a new game. The Godot client treats any non-200 `/step`
as "Step failed — backend error" and does not read the body. Such a handler
error used to be swallowed, and `/step` returned 200 with that day's physics
missing.

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
