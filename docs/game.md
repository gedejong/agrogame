---
module: agrogame.game
doc_type: module
references:
  - "ADR-003 — economic model (credits, price table, ledger)"
  - "ADR-004 — game loop and turn system"
key_classes: []
key_events: []
primary_tests:
  - tests/test_economic_ledger.py
  - tests/test_game_field.py
  - tests/test_game_turn.py
related_adrs: [ADR-002, ADR-003, ADR-004]
---

# Game

Game-layer state: economy, turn management, and the patch/field hierarchy
that wraps the science engine for player-driven runs. Kept separate from
`agrogame.sim` and `agrogame.soil` — the simulation has no concept of money,
turns, or scores.

## Submodules

- `agrogame.game.economy` — `EconomicLedger`, `PriceTable`, cost/revenue records (ADR-003).
- `agrogame.game.field` — `FieldManager`, `Field`, `Patch`, `PatchConfig` (ADR-002).
- `agrogame.game.turn` — `GameTurnManager`, `SeasonResult`, `PauseConfig`, `SeasonPhase` (ADR-004).

## Wiring

The API (`agrogame.api`) creates a `GameSession` with a `FieldManager` and an
`EconomicLedger`, then routes player actions through the manager. Each `Patch`
owns a `FullSimulationOrchestrator` from `agrogame.sim` that runs the daily
science step.
