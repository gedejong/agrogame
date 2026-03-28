# ADR-002: Multi-Field Architecture

## Status: Proposed

## Context

The current architecture ties one `FullSimulationOrchestrator` to one field. It owns a single `SoilProfile`, `SoilWaterState`, `NitrogenCycle`, `PhosphorusCycle`, `MicrobialBiomassModule`, `SoilChemistryModule`, `PhenologyModule`, `CanopyModule`, `RootModule`, `ManagementPlan`, and an `EventBus` -- all representing one physical field.

A farming game requires multiple fields so players can practice crop rotation across space (not just time), allocate limited resources (labor, water, equipment) between fields, and manage economic risk through diversification. The science engine must scale to N fields without architectural surgery.

The key constraint: `EventBus` is synchronous and module runtimes subscribe to it at construction time via `_wire_runtimes()`. Sharing an EventBus across fields would cause nitrogen events from field A to trigger handlers in field B. This is a hard no.

## Decision

**N fields, each with its own `FullSimulationOrchestrator` and independent `EventBus`. A new `FieldManager` class owns the collection and coordinates shared resources.**

Architecture:

```
FieldManager
  |-- Field[0]: FullSimulationOrchestrator (own EventBus)
  |-- Field[1]: FullSimulationOrchestrator (own EventBus)
  |-- ...
  |-- Field[N]: FullSimulationOrchestrator (own EventBus)
  |
  |-- SharedResources (labor_hours, water_allocation_mm, equipment_slots)
  |-- GlobalEventBus (farm-level events only: season_end, market_update)
```

Design rules:

1. **One `FullSimulationOrchestrator` per field.** No changes to the orchestrator internals. Each field is fully self-contained with its own `EventBus`, soil state, crop, and management plan. This is the existing architecture -- we just instantiate it N times.
2. **Fields step sequentially within a day tick.** `FieldManager.step_day()` loops over fields in index order, calling `orchestrator.step_day()` on each. No parallelism within a tick. Order does not matter because fields are physically independent (no lateral water flow, no nutrient transfer between fields).
3. **Shared resources are managed by `FieldManager`, not by orchestrators.** Before stepping fields, `FieldManager` validates that the day's management actions across all fields do not exceed available labor, water, or equipment. If they do, actions are queued or rejected -- the orchestrator never sees an invalid action.
4. **Global `EventBus` for farm-level events only.** `FieldManager` owns a separate `EventBus` for cross-cutting events: `SeasonEndEvent`, `MarketPriceUpdateEvent`, `BudgetWarningEvent`. Field-level orchestrators do not subscribe to this bus. The UI/economy layer does.
5. **Field identity is a string ID**, not an index. Fields can be added mid-game (buying land) or fallowed. The `FieldManager` stores fields in an `OrderedDict[str, FieldState]`.
6. **Target: 50 fields at < 1 GB memory, 150-day season in < 30 seconds.** Current orchestrator memory is ~10-15 MB per field (dominated by per-layer arrays across water/N/P/SOM). At 50 fields: ~750 MB. Step time is ~1-2 ms per field per day. At 50 fields x 150 days: ~7.5-15 seconds. Both within budget.

`FieldManager` public API:

```python
class FieldManager:
    def add_field(self, field_id: str, profile: SoilProfile, crop: CropPreset | None) -> None: ...
    def remove_field(self, field_id: str) -> None: ...
    def step_day(self, weather: WeatherDay) -> None: ...
    def harvest_field(self, field_id: str) -> HarvestResult: ...
    def get_snapshot(self, field_id: str) -> SoilSnapshot: ...
    def to_dict(self) -> dict: ...  # for ADR-001 save format
    def from_dict(cls, data: dict) -> FieldManager: ...
```

## Consequences

**Positive:**
- Zero changes to `FullSimulationOrchestrator`, `EventBus`, or any existing module. The multi-field layer is purely additive.
- Field isolation is guaranteed by construction. No event bus cross-talk, no shared mutable state between fields.
- Adding/removing fields at runtime is straightforward -- just instantiate/destroy an orchestrator.
- Performance scales linearly. Profiling one field predicts N-field performance accurately.

**Negative:**
- Memory scales linearly with field count. Each field duplicates the full module stack. At 50 fields this is ~750 MB -- acceptable but not cheap. If we ever need 500+ fields (e.g., regional simulation), we'll need to share immutable data (soil profile templates, crop parameter tables).
- Sequential stepping means a 50-field tick takes 50x a single-field tick. Parallelism (multiprocessing) is possible later because fields are independent, but adds complexity. Not needed until step time exceeds 100 ms per tick.
- Shared resource validation in `FieldManager` adds a new coordination layer that must be tested separately. Resource conflicts (two fields requesting irrigation on the same day with insufficient water) need clear resolution rules.

## Alternatives Considered

**Single orchestrator managing N soil profiles.** Would require deep refactoring of `FullSimulationOrchestrator` to loop over profiles internally, handle per-field EventBus routing, and manage per-field crop/management state. Invasive, error-prone, and unnecessary. Rejected.

**Shared `EventBus` with field-tagged events.** Every event carries a `field_id`, and handlers filter by field. This is fragile -- a handler that forgets to filter processes events from all fields, causing silent corruption. The isolation guarantee is opt-in instead of structural. Rejected.

**Process-per-field parallelism from day one.** Each field runs in a separate process with its own memory space. Provides perfect isolation and parallelism but adds IPC overhead for shared resource coordination, complicates save/load, and makes debugging harder. Over-engineering for 50 fields where sequential stepping takes <30s. Rejected for V1.

**Lazy field instantiation.** Only instantiate orchestrators for fields that have active crops; fallow fields are just a snapshot. Saves memory but adds lifecycle complexity and edge cases around re-instantiation. Premature optimization. Rejected.
