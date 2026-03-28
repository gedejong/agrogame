# ADR-002: Multi-Field Architecture

## Status: Proposed

## Context

The current architecture ties one `FullSimulationOrchestrator` to one field. It owns a single `SoilProfile`, `SoilWaterState`, `NitrogenCycle`, `PhosphorusCycle`, `MicrobialBiomassModule`, `SoilChemistryModule`, `PhenologyModule`, `CanopyModule`, `RootModule`, `ManagementPlan`, and an `EventBus` -- all representing one physical field.

A farming game requires multiple fields so players can practice crop rotation across space (not just time), allocate limited resources (labor, water, equipment) between fields, and manage economic risk through diversification. Within a single field, spatial variability matters: soil texture, drainage, and organic matter vary across a field, and players may want to manage sub-regions differently (e.g., irrigate the sandy corner more aggressively, apply variable-rate fertilizer). The science engine must scale to N fields with M patches each without architectural surgery.

The key constraint: `EventBus` is synchronous and module runtimes subscribe to it at construction time via `_wire_runtimes()`. Sharing an EventBus across fields or patches would cause nitrogen events from one unit to trigger handlers in another. This is a hard no.

## Decision

**N fields, each containing M patches. Each patch has its own `FullSimulationOrchestrator` and independent `EventBus`. A `FieldManager` class owns the two-level hierarchy and coordinates shared resources.**

Architecture:

```
FieldManager
  |-- Field[0] (field_id, area_ha, geometry metadata)
  |     |-- Patch[0]: FullSimulationOrchestrator (own EventBus)
  |     |-- Patch[1]: FullSimulationOrchestrator (own EventBus)
  |     |-- ...
  |     |-- Patch[M]: FullSimulationOrchestrator (own EventBus)
  |
  |-- Field[1]
  |     |-- Patch[0]: FullSimulationOrchestrator (own EventBus)
  |     |-- ...
  |
  |-- Field[N]
  |     |-- ...
  |
  |-- SharedResources (labor_hours, water_allocation_mm, equipment_slots)
  |-- GlobalEventBus (farm-level events only: season_end, market_update)
```

Design rules:

1. **One `FullSimulationOrchestrator` per patch.** No changes to the orchestrator internals. Each patch is fully self-contained with its own `EventBus`, soil state, crop, and management plan. This is the existing architecture -- we just instantiate it N x M times.
2. **A `Field` contains N `Patch` objects.** Each patch has its own soil profile, active crop, and management plan. A field is a logical grouping with shared metadata (location, total area, ownership). Each patch has a `fraction` attribute (summing to 1.0 across the field) that determines its share of the field area.
3. **Field-level actions distribute proportionally across patches.** When a management action targets a field (e.g., irrigate field_01 with 25 mm), `FieldManager` distributes the action to all patches in that field. Distribution is proportional to patch area fractions by default. Patch-level actions allow targeted management of individual patches (e.g., apply extra nitrogen only to the sandy patch).
4. **Patches step sequentially within a day tick.** `FieldManager.step_day()` loops over fields, then over patches within each field, calling `orchestrator.step_day()` on each. No parallelism within a tick. Order does not matter because patches are physically independent (see Limitations below).
5. **Shared resources are managed by `FieldManager`, not by orchestrators.** Before stepping fields, `FieldManager` validates that the day's management actions across all fields and patches do not exceed available labor, water, or equipment. If they do, actions are queued or rejected -- the orchestrator never sees an invalid action.
6. **Global `EventBus` for farm-level events only.** `FieldManager` owns a separate `EventBus` for cross-cutting events: `SeasonEndEvent`, `MarketPriceUpdateEvent`, `BudgetWarningEvent`. Patch-level orchestrators do not subscribe to this bus. The UI/economy layer does.
7. **Field identity is a string ID; patch identity is field_id + patch index.** Fields can be added mid-game (buying land) or fallowed. The `FieldManager` stores fields in an `OrderedDict[str, Field]`. Patches within a field are stored in a list, addressed by index.
8. **Target: 50 fields x ~5 patches = 250 orchestrators at < 2 GB memory, 150-day season in < 60 seconds.** Current orchestrator memory is ~6-8 MB per instance (dominated by per-layer arrays across water/N/P/SOM). At 250 orchestrators: ~1.5-2.0 GB. Step time is ~1-2 ms per orchestrator per day. At 250 orchestrators x 150 days: ~37-75 seconds. Both within budget, though closer to the edge than single-patch-per-field. If memory pressure is observed, sharing immutable data (crop parameter tables, soil profile templates) across patches within a field is the first optimization.

`FieldManager` public API:

```python
class FieldManager:
    def add_field(self, field_id: str, patches: list[PatchConfig]) -> None: ...
    def remove_field(self, field_id: str) -> None: ...
    def add_patch(self, field_id: str, patch_config: PatchConfig) -> int: ...
    def step_day(self, weather: WeatherDay) -> None: ...
    def apply_field_action(self, field_id: str, action: ManagementAction) -> None: ...
    def apply_patch_action(self, field_id: str, patch_idx: int, action: ManagementAction) -> None: ...
    def harvest_field(self, field_id: str) -> list[HarvestResult]: ...
    def get_field_snapshot(self, field_id: str) -> FieldSnapshot: ...
    def get_patch_snapshot(self, field_id: str, patch_idx: int) -> PatchSnapshot: ...
    def to_dict(self) -> dict: ...  # for ADR-001 save format
    def from_dict(cls, data: dict) -> FieldManager: ...
```

**Save format cross-reference (ADR-001):** The save file's `fields` array contains one object per field, and each field object contains a `patches` array of patch snapshots. Each patch snapshot includes its own `soil_snapshot`, `root_state`, `active_crop`, `management_plan`, and `fraction`:

```json
{
  "fields": [
    {
      "field_id": "field_01",
      "area_ha": 5.0,
      "patches": [
        {
          "patch_idx": 0,
          "fraction": 0.6,
          "soil_profile_key": "clay_loam_3layer",
          "active_crop": "winter_wheat",
          "soil_snapshot": { "..." },
          "root_state": { "..." },
          "management_plan": { "..." }
        },
        {
          "patch_idx": 1,
          "fraction": 0.4,
          "soil_profile_key": "sandy_loam_3layer",
          "active_crop": "winter_wheat",
          "soil_snapshot": { "..." },
          "root_state": { "..." },
          "management_plan": { "..." }
        }
      ],
      "crop_history": ["maize", "soybean"]
    }
  ]
}
```

## Limitations

**V1 treats patches as independent vertical columns with no lateral water or nutrient exchange.** There is no lateral flow of water, nitrogen, or phosphorus between patches -- each patch is a standalone 1-D soil column. This is an intentional simplification: lateral flow modeling (e.g., Richards equation in 2-D, topography-driven runoff redistribution) adds significant complexity and computational cost that is not justified for a game-scale simulation in V1.

This simplification means V1 cannot represent:
- Downslope accumulation of runoff or leachate from upslope patches.
- Lateral subsurface water movement between patches with different water tables.
- Nutrient transport via surface or subsurface lateral flow.

To avoid painting ourselves into a corner, the `Patch` interface exposes per-layer soil water content (`theta`) and nitrogen concentration (`NO3_kg_ha`, `NH4_kg_ha`) via read-only accessors. This makes future gradient-driven lateral exchange between adjacent patches possible without breaking the patch abstraction -- a coupling layer can read neighboring states, compute fluxes, and inject them as source/sink terms into each patch's next time step.

## Consequences

**Positive:**
- Zero changes to `FullSimulationOrchestrator`, `EventBus`, or any existing module. The multi-field and sub-field layer is purely additive.
- Patch isolation is guaranteed by construction. No event bus cross-talk, no shared mutable state between patches.
- Adding/removing fields and patches at runtime is straightforward -- just instantiate/destroy orchestrators.
- Performance scales linearly. Profiling one orchestrator predicts N-orchestrator performance accurately.
- Sub-field patches enable variable-rate management, spatial heterogeneity, and more realistic field representation without changing the simulation core.
- The lateral-coupling-ready interface means V2 can add inter-patch flow without breaking the architecture.

**Negative:**
- Memory scales linearly with total patch count. Each patch duplicates the full module stack. At 250 orchestrators this is ~1.5-2.0 GB -- acceptable but not cheap. Sharing immutable data within a field is the first optimization if needed. If we ever need 500+ fields (e.g., regional simulation), further structural sharing is required.
- Sequential stepping means a 250-orchestrator tick takes 250x a single-orchestrator tick. Parallelism (multiprocessing) is possible later because patches are independent, but adds complexity. Not needed until step time exceeds 100 ms per tick.
- Shared resource validation in `FieldManager` adds a coordination layer that must be tested separately. Resource conflicts (two fields requesting irrigation on the same day with insufficient water) need clear resolution rules.
- The two-level hierarchy (fields and patches) adds API surface and conceptual overhead compared to a flat field list. Justified by the spatial management use cases.
- Independent patches cannot represent lateral hydrological processes. This is acceptable for V1 game mechanics but limits realism for sloped or poorly-drained fields.

## Alternatives Considered

**Single orchestrator managing N soil profiles.** Would require deep refactoring of `FullSimulationOrchestrator` to loop over profiles internally, handle per-field EventBus routing, and manage per-field crop/management state. Invasive, error-prone, and unnecessary. Rejected.

**Shared `EventBus` with field-tagged events.** Every event carries a `field_id`, and handlers filter by field. This is fragile -- a handler that forgets to filter processes events from all fields, causing silent corruption. The isolation guarantee is opt-in instead of structural. Rejected.

**Process-per-field parallelism from day one.** Each field runs in a separate process with its own memory space. Provides perfect isolation and parallelism but adds IPC overhead for shared resource coordination, complicates save/load, and makes debugging harder. Over-engineering for 250 orchestrators where sequential stepping takes <60s. Rejected for V1.

**Lazy field instantiation.** Only instantiate orchestrators for fields that have active crops; fallow fields are just a snapshot. Saves memory but adds lifecycle complexity and edge cases around re-instantiation. Premature optimization. Rejected.

**Flat field list without sub-field patches.** Simpler API and lower orchestrator count, but forces players to create separate "fields" to represent spatial variability within a single physical field. This conflates field identity with soil heterogeneity and makes field-level operations (sell a field, report per-field yield) awkward. Rejected in favor of the two-level hierarchy.

**Full 2-D lateral flow from day one.** Coupling patches via lateral water and nutrient exchange in V1 would add substantial complexity (topology definitions, flow routing, numerical stability of coupled equations) for marginal gameplay benefit. The independent-column simplification is standard practice in many crop models (DSSAT, APSIM) and sufficient for game-scale decisions. Rejected for V1; the patch interface is designed to enable this in V2.
