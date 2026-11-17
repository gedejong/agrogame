---
module: agrogame.game
doc_type: module
references:
  - "ADR-003 — economic model (credits, price table, ledger)"
  - "ADR-017 — act any day, fast-forward interrupted by in-season alerts (supersedes ADR-004)"
key_classes: []
key_events: []
primary_tests:
  - tests/test_economic_ledger.py
  - tests/test_game_field.py
  - tests/test_game_turn.py
related_adrs: [ADR-002, ADR-003, ADR-017]
---

# Game

Game-layer state: economy, turn management, and the patch/field hierarchy
that wraps the science engine for player-driven runs. Kept separate from
`agrogame.sim` and `agrogame.soil` — the simulation has no concept of money,
turns, or scores.

## Submodules

- `agrogame.game.economy` — `EconomicLedger`, `PriceTable`, cost/revenue records (ADR-003).
- `agrogame.game.field` — `FieldManager`, `Field`, `Patch`, `PatchConfig` (ADR-002).
- `agrogame.game.turn` — `PauseDetector`, `PauseConfig`, `PauseEvent`, `GameTurnManager`, `SeasonResult`, `SeasonPhase` (ADR-017).

## Wiring

The API (`agrogame.api`) creates a `GameSession` with a `FieldManager` and an
`EconomicLedger`, then routes player actions through the manager. Each `Patch`
owns a `FullSimulationOrchestrator` from `agrogame.sim` that runs the daily
science step.

## In-season alerts (#470, ADR-017)

`PauseDetector` runs after every `/step` day, for every field over all of its
patches, and reads only that day's recorded stress events: drought from
`WaterStressComputed` (Ks < 0.4), nitrogen from the N `NutrientStressComputed`
(< 0.9, emerged to flowering), and a frost notice when tomorrow's minimum is
below the crop's `frost_threshold_c` in the canopy damage stages. Each
(field, reason) has an onset/re-arm latch, and interrupts on one field are
more than 3 days apart, with a suppressed reason deferred rather than dropped.
`PauseConfig` holds the playtest-calibrated alert parameters; none is a model
constant. The detector subscribes to no bus, so it cannot change a simulated
value or stack handlers across seasons.
