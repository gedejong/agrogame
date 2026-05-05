# ADR-008: Import layering and shared-type homes

## Status

Accepted (#300, supersedes the legacy intent embedded in the previous `.importlinter`).

## Context

`.importlinter` was migrated from the legacy `[contract:<name>]` headers to the v2-required `[importlinter:contract:<name>]` form in #297. The format bug had been silently passing every contract for an unknown period — once enforcement turned on, six of the nine pre-existing contracts came back broken (#300). The breakages fell into four shapes:

1. **`agrogame.sim.calendar_events.DayTick`** was imported from 14 domain runtimes plus tests, dragging the simulation composition root into every contract that forbids domain → `sim.*` edges.
2. **`PhenologyStage`, `CropPhenologyParams`, `GrowthStageThresholds`, `CanopyParams`** lived under `agrogame.soil.{phenology,canopy}` but were imported by `agrogame.plant.{biomass, roots, presets}` — a `plant_vs_soil` violation that's actually a misplaced-type problem.
3. **`agrogame.atmosphere.et.runtime`** stored concrete soil/plant types (`SoilProfile`, `SoilWaterState`, `CascadingBucketWaterModel`, `RootState`, `CanopyModule`) as dataclass fields, even though the runtime only used Protocol-level operations on them.
4. **`agrogame.soil.<subdomain>` runtimes** subscribe to `agrogame.plant.events` / `agrogame.plant.roots.events` / `agrogame.plant.stress` — legitimate event-driven coupling that the contracts as written disallow.

The previous ordering on `domain_layers` was also reversed for import-linter's `layers` semantics (earlier entries are higher; lower entries can't reach upward), so plant/atmosphere couldn't import each other in either direction.

## Decision

### Layer order

```
agrogame.atmosphere   (highest)
agrogame.plant
agrogame.soil
agrogame.weather      (lowest)
```

Derived from the existing `forbidden` contracts:

- `plant_independence` says plant ↛ atmosphere ⇒ atmosphere > plant.
- `soil_plant_direction` says soil ↛ plant ⇒ plant > soil.
- `weather_independence` says weather ↛ everything ⇒ weather is the floor.

ET (atmosphere) genuinely orchestrates plant + soil + weather inputs, so it sits at the top. Weather is the foundational driver, so it sits at the bottom.

### Shared-type homes

| Type | New home | Old location | Status |
|------|----------|--------------|--------|
| `DayTick`, `Phase` | `agrogame.events.calendar` | `agrogame.sim.calendar_events` | Old module is a re-export shim. |
| `PhenologyStage` | `agrogame.params.phenology` | `agrogame.soil.phenology.types` | Old `types.py` re-exports. |
| `CropPhenologyParams`, `GrowthStageThresholds` | `agrogame.params.phenology` | `agrogame.soil.phenology.params` | Old `params.py` is a re-export shim. |
| `CanopyParams` | `agrogame.params.canopy` | `agrogame.soil.canopy.params` | Old `params.py` re-exports + keeps `cardinal_temp_factor`. |

`agrogame.events.calendar` deliberately does **not** import `DailyDrivers` from `agrogame.soil.water.types` — the `DayTick.drivers` field is annotated as a forward-reference (`Any | None`) so the `events_isolated` contract stays green.

### ET dependency inversion

`ETRuntime` (`agrogame/atmosphere/et/runtime.py`) holds its dependencies via Protocols defined in `agrogame/atmosphere/et/ports.py`:

| Field | Protocol |
|-------|----------|
| `profile` | `WaterProfile` |
| `water_state` | `WaterState` |
| `water_model` | `WaterActuator` |
| `roots_state` | `RootDistribution` (new) |
| `canopy` | `CanopyView` (new) |

The orchestrator (`agrogame/sim/orchestrator.py`) wires concrete soil/plant instances into the runtime via `cast()` at the construction boundary. There is no runtime behavior change — the casts existed previously inside the runtime body around `actual_et()`.

### `ignore_imports` allowlists

Three contracts carry an `ignore_imports` block listing legitimate cross-domain reads of *event-payload types*:

| Contract | Pattern | Count |
|----------|---------|------:|
| `soil_plant_direction` | soil → plant.events / plant.roots.events / plant.stress | 15 |
| `domain_layers` | (mirror of soil_plant_direction — same edges) | 15 |
| `soil_subdomain_independence` | canopy → phenology, canopy → water.events, nitrogen → water.events, water.legacy → canopy.interception | 6 |
| `plant_vs_soil` | plant.roots.runtime → soil.phenology.PhenologyModule | 1 |

The shared rationale: each entry is a publisher/subscriber edge where the subscriber reads an event-payload type from the publisher's package. Relocating those payload types into a shared `events.<domain>` package would be a separate, larger refactor. The current allowlist captures the surface so future drift (any *new* edge) fails the gate.

`agrogame.soil.water.legacy → agrogame.soil.canopy.interception` is whitelisted explicitly because the legacy water model is slated for removal (#288 / soil-water audit umbrella). When that module is excised, this entry should be deleted.

## Consequences

### Easier

- **Drift detection**: every `lint-imports` run evaluates all 10 contracts. New cross-domain edges fail CI.
- **Plant/soil shared types** are clearly homed: `agrogame.params.phenology` and `agrogame.params.canopy` are the canonical locations. New code should import from there directly; the old soil-side modules remain only as re-export shims.
- **ET wiring** is decoupled — adding an alternate water model or canopy implementation no longer requires changes inside `atmosphere/et/runtime.py`. The orchestrator simply passes a different concrete object that satisfies the Protocols.

### Harder

- **Old import paths are still permitted** via the re-export shims. New contributors might import `from agrogame.soil.phenology import PhenologyStage` instead of the canonical `from agrogame.params.phenology import PhenologyStage`. A linter rule (potentially a custom ruff plugin) could block the legacy path; deferred until this becomes a real problem.
- **`ignore_imports` allowlists are maintained by hand**. Each is documented with a comment block in `.importlinter`; reviewers must update the comment when adjusting an allowlist.
- The `cast()` calls in the orchestrator are slightly noisy. Replacing them with explicit adapter classes is a possibility if the construction site grows.

### Follow-up work

- Excise `agrogame.soil.water.legacy` (umbrella #288) and remove its `ignore_imports` entry from `soil_subdomain_independence`.
- If the soil → plant.events subscription pattern remains stable, consider relocating those event types into `agrogame.events.plant` so the allowlists shrink. Track separately when the count is large enough to justify the churn.
- Promote a custom ruff/flake8 rule to forbid legacy import paths once the back-compat shims have been in place long enough to migrate downstream consumers.

## Alternatives Considered

### Bulk-fill `ignore_imports` instead of relocating types

Rejected for `DayTick` and the phenology/canopy types: these are real type misplacements, and relocating them is a one-time mechanical change that turns multiple contracts green simultaneously. The `ignore_imports` allowlist is reserved for cases where the cross-edge is genuinely intrinsic (event subscription) rather than a fixable misplacement.

### Strictly-layered architecture (no `ignore_imports`)

Rejected: would require relocating every `*.events` module that has a cross-domain subscriber into a shared `events.<domain>` package, plus reworking the soil → plant.stress reads. The cost-to-benefit ratio is poor — the existing event subscriptions are already loosely coupled in practice (the soil-side subscriber stores nothing from the plant package; it just consumes `BaseEvent` payloads).

### Move everything into `agrogame.events` and `agrogame.params`

Rejected as a wholesale solution: would be a massive churn for marginal architectural benefit. The selective relocation in #300 captures the cases that matter.

## References

- Parent issue: #293 (Phase 4 epic)
- Resolution issue: #300
- Discovered in: #297 (initial format migration)
- Format-bug origin: import-linter v2 changelog (legacy section header silently ignored)
