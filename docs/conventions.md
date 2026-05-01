# Code Conventions

Concise reference for AgroGame Python conventions. Aimed at someone landing a
new module: read this in five minutes, then go build. Documents what the
codebase already does — not aspirational future state. Drift fixes are tracked
under audit umbrella **#280**.

For frontend (Godot/GDScript) conventions, see [CLAUDE.md](../CLAUDE.md) §
"Code Style (GDScript)".

## 1. Module shape

Canonical layout for a domain module under `agrogame/soil/` or `agrogame/plant/`:

```
agrogame/<area>/<module>/
  __init__.py     # public API exports + __all__
  params.py       # frozen *Params dataclass(es)
  state.py        # mutable *State dataclass(es)
  module.py       # *Module — pure logic; subscribes nothing
  runtime.py      # *Runtime — wires the module to the EventBus
  events.py       # frozen domain events (BaseEvent subclasses)
```

Reference implementations: `agrogame/soil/aggregation/`, `agrogame/soil/biopores/`,
`agrogame/soil/micronutrients/`, `agrogame/soil/redox/`, `agrogame/plant/roots/`.

### Documented exceptions

| Module | Deviation | Reason |
|--------|-----------|--------|
| `agrogame/sim/` | Flat (`orchestrator.py`, `engine.py`, `builder.py`, `calendar.py`, `management.py`) | Composition root — no domain state of its own |
| `agrogame/soil/som/` | `pools.py` instead of `state.py` | Three-pool RothC names the pool, not generic state |
| `agrogame/soil/microbes/` | `biomass.py` + `responses.py` | Pre-canonical; rename tracked in #288 |
| `agrogame/soil/water/` | Adds `models/` sub-package, `legacy.py`, `scs.py`, `constants.py`, `types.py` | Multiple water-balance implementations + SCS curve number table |
| `agrogame/soil/chemistry/` | Only `module.py` + `events.py` | No mutable state yet; tracked in #288 |
| `agrogame/soil/pore_network/`, `gas_diffusion/`, `biopores/` | `runtime.py` may be present but not orchestrator-wired | Wiring deferred to #284 |
| `agrogame/soil/canopy/`, `phenology/`, `agrogame/plant/roots/` | `factory.py` + `types.py` instead of `params.py` + `state.py` | Older convention; rename optional |
| `agrogame/atmosphere/` | Only contains `et/` | Single-child wrapper — collapse if no second child appears |

When introducing a new module, follow the canonical layout. When deviating,
add a row to the table above.

## 2. Naming

| Concept | Convention | Example |
|---------|-----------|---------|
| Immutable parameters | `<Domain>Params` (frozen `@dataclass`) | `BioporeParams`, `PoreNetworkParams` |
| Mutable state | `<Domain>State` (`@dataclass`, mutable lists) | `BioporeState`, `RedoxState` |
| Pure-logic class | `<Domain>Module` | `BioporeModule`, `PoreNetworkModule` |
| Event-bus runtime | `<Domain>Runtime` | `BioporesRuntime`, `AggregationRuntime` |
| Domain events | `*Updated` / `*Applied` / `*Occurred` / `*Changed` | `RootTurnoverOccurred` |
| Diagnostic events | `*Computed` | `WaterStressComputed`, `PoreNetworkComputed` |

### Pydantic vs dataclass

- **Pydantic `BaseModel`** only at I/O boundaries: configuration loading
  (`agrogame/soil/models.py`, `agrogame/params/models.py`), the API
  (`agrogame/api/models.py`), and YAML preset loaders.
- **`@dataclass`** for everything internal — module state, params, events,
  ad-hoc result records.

Rationale: Pydantic carries a validation/serialization tax that's only
worthwhile at trust boundaries. Internal flow is faster and clearer with
plain dataclasses.

## 3. Method names

`daily_step(...)` is the canonical name for the once-per-day computation on a
`*Module`. Existing aliases (`update_daily`, `step_day`, `compute`, `step`)
predate the convention — rename tracked in **#282**.

A typical signature:

```python
class BioporeModule:
    def daily_step(self, profile: SoilProfile, ...) -> None: ...
```

The runtime calls it from a `DayTick` handler. Modules don't subscribe to
events themselves — that's the runtime's job.

## 4. Event tense

Past-tense for **state changes**: `WaterDrained`, `RootDepthChanged`,
`MineralizationOccurred`, `FrostDamageApplied`, `BioporeCreated`.

`*Computed` only for **derived diagnostics** with no state mutation:
`WaterStressComputed`, `NutrientStressComputed`, `MicrobialActivityComputed`.

Some legacy events still use the present tense (`PoreNetworkComputed`,
`LAIUpdated`, `AggregateStructureUpdated`, `SoilPHUpdated`). These are
flagged for renaming in **#283**; new events must follow this rule.

When in doubt: did the event signal a side-effect on a `*State` instance?
→ past tense (`*Updated`, `*Occurred`). Did the event carry a value derived
from current state? → `*Computed`.

Events are frozen `@dataclass` subclasses of `agrogame.events.BaseEvent`.
Payloads must be lightweight (lists/tuples of primitives, not whole state
objects).

## 5. Variable naming

- **`theta`** in code for volumetric water content (m³/m³). Used everywhere
  in water/nutrient/micronutrient modules.
- **`soil_moisture`** only in user-facing strings: dashboard labels, API
  documentation, log messages aimed at the player.
- `water_content` is **not** an internal name — kept only in user-docs prose.

This split keeps numerical code consistent (single name across thousands of
references) while still letting UX surface a friendlier label.

## 6. Test layout

```
tests/
  unit/test_*.py            # pure unit tests (no I/O, no orchestrator)
  integration/test_*.py     # multi-module simulation slices, realism
  e2e/*.spec.ts             # Playwright frontend tests
  conftest.py               # shared fixtures
```

Currently many unit tests live as **flat `tests/test_*.py` files**. Relocation
to `tests/unit/` is mechanical and tracked in **#287**. New unit tests should
go in `tests/unit/` directly.

Realism tests in `tests/integration/test_realism.py` must:
- Cite a literature range or source in a comment.
- Assert a numeric range, not just `> 0`.

Use `tests/conftest.py` fixtures for anything cross-cutting. Local helpers
(like `_loam_profile()`) duplicated across test modules should be promoted —
extraction tracked in **#286**.

## 7. Coverage exclusions

`.coveragerc` excludes:

- **Frontend-adjacent** (`game/`) — Godot/GDScript not measured by `pytest --cov`.
- **Optional-extras** (`dashboard/`, `plots/`) — heavy deps imported locally
  inside guarded functions; full execution requires `poetry install -E dashboard`.
- **CLI shells** — entry-point modules whose body is `cli()` glue.

Criterion when proposing a new exclusion: is the code a thin wrapper around
an optional dep, or a CLI bootstrap that's exercised by smoke tests but not
worth full coverage? If yes, add to `.coveragerc` and note here.

The base coverage threshold is **92%** (was 97% before optional-extras
exclusions; current effective coverage hovers around 95%).

## 8. Pre-commit and CI

Pre-commit (fast, ~5 s): `black`, `ruff`, `flake8`, `gdlint`, `gdformat`,
file-coverage check.

Manual stage (CI mirror): `mypy`, `xenon`, `importlinter`, `deptry`, full
`pytest`, GUT (Godot tests). Run with
`pre-commit run --hook-stage manual --all-files`.

`vulture --min-confidence 80` runs in CI (`quality.yml`) but **not** in
pre-commit by design — false positives on dataclass fields and event
payloads make the local hook noisy. Safe to add later if a config tightens
the false-positive rate.

## 9. Where things live

| You're looking for | Path |
|--------------------|------|
| Soil-water-balance day step | `agrogame/soil/water/models/cascading.py` |
| Per-layer pore size distribution | `agrogame/soil/pore_network/state.py` |
| Daily orchestration sequence | `agrogame/sim/orchestrator.py:FullSimulationOrchestrator` |
| YAML soil presets | `data/soils/presets.yaml` (or root `soils/presets.yaml`) |
| Crop presets | `data/crops/presets.yaml` |
| Climate presets | `data/climate/presets.yaml` |
| Public events | `agrogame/<area>/<module>/events.py` |
| Architecture decisions | `docs/adr/ADR-*.md` |

When you find code that violates these conventions, first check the
exception table in §1. If it's not there, file an audit follow-up issue
labelled `audit:#280` with a clear "what / why / where".
