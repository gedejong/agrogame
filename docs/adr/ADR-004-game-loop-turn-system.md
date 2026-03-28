# ADR-004: Game Loop and Turn System

## Status: Proposed

## Context

The simulation engine currently exposes a `step_day()` method on `SimulationOrchestrator` and `FullSimulationOrchestrator` that advances the model one calendar day at a time. Callers (tests, CLI, Streamlit dashboard) loop over days manually. This is fine for scientific validation but unusable as a game: there are no decision points, no pacing, no tension, and no consequences. A 150-day wheat season is 150 clicks of nothing. We need a turn structure that creates meaningful player decisions at the right cadence — not too frequent (boring micro-management), not too sparse (loss of agency).

The existing `ManagementPlan` dataclass already models a pre-scheduled list of `ManagementEvent` items (irrigation, fertilization) keyed by day number. This gives us a natural foundation: the player commits a plan, then watches it play out.

## Decision

**Season-based turns with mid-season event pauses.**

The game loop is structured as follows:

1. **Pre-season planning phase.** The player selects crop(s) per field, sets a `ManagementPlan` (irrigation schedule, fertilizer applications), and confirms. Crop choice is locked for the season once confirmed — no replanting mid-season.

2. **Season execution phase.** The orchestrator fast-forwards through all days in the season by calling `step_day()` in a tight loop. The simulation runs to completion unless a **pause event** fires. Pause events are significant in-season occurrences that demand player response:
   - Frost warning (temperature below crop tolerance threshold)
   - Drought (soil moisture below wilting point for N consecutive days)
   - Pest/disease outbreak (future module)
   - Nutrient deficiency alert (N or P stress exceeding threshold)

3. **Mid-season adjustment.** When a pause event fires, the player may adjust irrigation and fertilizer schedules for the remaining days. They may **not** change crop choice, field allocation, or soil amendments. This keeps consequences meaningful while allowing reactive play.

4. **End-of-season settlement.** After the final day, the engine computes harvest yield, economic outcome (ADR-003), and soil state carry-over. The player reviews results and enters the next pre-season planning phase.

5. **No undo.** A confirmed plan executes. Bad decisions compound. This is the core tension mechanic — the player must learn the agronomy to succeed, not save-scum their way through.

Implementation details:

- A new `GameTurnManager` class wraps `FullSimulationOrchestrator`. It owns the loop, listens for pause events via `EventBus`, and yields control back to the caller (API layer) at each pause point.
- Pause events are a new `PauseEvent(BaseEvent)` subclass with a `reason` enum and `context` dict.
- The `ManagementPlan` gains a `revise(from_day: int, new_events: list[ManagementEvent])` method for mid-season adjustments.
- Season boundaries are defined by `Calendar` (already exists in `agrogame.sim.calendar`). A "turn" maps to one agronomic season (e.g., spring planting through fall harvest).
- Multi-year play is a sequence of season turns. Inter-season decisions (crop rotation, soil amendments, field expansion) happen in the pre-season phase.

## Consequences

**Positive:**
- Clear decision-consequence loop that makes agronomy knowledge a competitive advantage.
- Fast-forward execution means the player is never waiting for simulation — they are either deciding or watching results.
- `ManagementPlan` already exists and needs only minor extension, not a rewrite.
- Pause events reuse the `EventBus` infrastructure; no new pub/sub mechanism needed.
- Season granularity matches real farming cadence and keeps game sessions short (~5 min per season).

**Negative:**
- Players cannot experiment with day-by-day control — the system is deliberately coarser. Power users (agronomists) may find this limiting.
- Pause event thresholds must be carefully tuned: too many pauses break flow, too few remove agency. This requires playtesting.
- The "no undo" design is polarizing. Some players will find it punishing. We accept this — the alternative (save/load) removes all strategic depth.
- Mid-season adjustment logic adds complexity to `ManagementPlan` (must handle partial plan replacement without invalidating already-executed days).

## Alternatives Considered

**Daily turns (player acts every simulated day).** Rejected. 150+ clicks per season with most days requiring no action. Tedious. Real farmers do not make decisions daily — they plan ahead and react to events.

**Weekly turns (fixed 7-day intervals).** Rejected. Arbitrary grouping that does not align with agronomic events. A frost on day 3 of a week would not be visible until day 7. Breaks realism and removes urgency.

**Fully autonomous (set plan, never pause).** Rejected. Removes player agency during the season entirely. The game becomes "set and forget" with no mid-season tension. Pause events are what make seasons interesting.

**Real-time with pause (Factorio-style).** Rejected. Requires continuous rendering of simulation state, which conflicts with the turn-based economic model (ADR-003) and adds frontend complexity (ADR-005) for minimal gameplay benefit in a farming context.
