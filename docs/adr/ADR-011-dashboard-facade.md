# ADR-011: Dashboard façade for in-process engine consumption

## Status

Accepted (#309).

## Context

The Streamlit dashboard (`agrogame/dashboard/`) ran the simulation
engine in-process and gripped its internal types directly. Imports
spanned six soil sub-packages plus plant, atmosphere, and sim:

```
agrogame/dashboard/app.py        → soil.models.SoilProfile
agrogame/dashboard/charts.py     → soil.models.SoilProfile
agrogame/dashboard/export.py     → soil.models.SoilProfile
agrogame/dashboard/simulation.py → soil.{models,loader,microbes.events,
                                        nitrogen.cycle,phenology.types,
                                        water.events,water.types},
                                   plant.events, atmosphere.et,
                                   sim.orchestrator, weather
```

Beyond type imports, `simulation.py` subscribed to **six engine event
types** (`MicrobialActivityComputed`, `EnzymeGroupTotalsComputed`,
`EvaporationTaken`, `TranspirationByLayer`, `NutrientStressComputed`,
`WaterStressComputed`) — making the dashboard a silent stakeholder in
every payload-shape decision. Surfaced by the SoilProfile graph trace
(graphify run, 2026-05-06) as the most striking layering smell on the
codebase.

#303 already tracks the analogous question for the HTTP API. The
dashboard sits one layer further up — same shape, larger reach, no
existing contract.

## Decision

Carve `agrogame/api/dashboard_facade.py` as the **single surface** the
dashboard talks to. Every engine-internal type the dashboard names is
re-exported from there. The event-subscriber wiring + history-dict
builder lifts out of `dashboard/simulation.py` into the façade as
`DashboardSimulationRun`. The dashboard never imports from
`agrogame.{soil, plant, weather, atmosphere, sim}.*` again.

A new import-linter contract (`dashboard_isolation`) enforces the
invariant; `allow_indirect_imports = true` lets the façade act as a
wormhole that re-exports stable types without the contract chasing the
re-export's own imports.

### Why a façade in `agrogame.api`, not `agrogame.dashboard.adapters`

The HTTP API and the dashboard are both consumers of the public engine
surface — Godot via HTTP, the dashboard in-process. Putting the façade
under `agrogame.api` makes that explicit: `agrogame.api` is the public
contract surface, and `dashboard_facade` is "in-process transport"
parallel to `routes.py` ("HTTP transport"). New consumers (a Jupyter
notebook helper, a CLI exporter) get the same affordance for free.

### Why re-export, not wrap

For the eight engine types the dashboard names today (`SoilProfile`,
`DailyDrivers`, `WeatherRecord`, `PhenologyStage`, `EtParams`,
`Evapotranspiration`, `EnzymeGroupTotalsComputed`, `NitrogenCycle`), wrapping
each in a façade-owned dataclass would double the work without
benefit — these are stable Pydantic models and frozen dataclasses. The
re-export pattern means rename them in the engine and the façade
breaks loudly with an import error; the dashboard recovers as soon as
the façade re-export is updated. If a downstream type starts
churning, that specific re-export can be replaced with a wrapped façade
type without touching the dashboard.

### Rejected: HTTP-only consumption (Option B)

The original issue listed "dashboard talks to API only" as Option B.
Rejected because (a) the API is currently game-session-oriented, not
analyst-oriented — closing the gap to expose per-day water-by-layer /
enzyme groups / stress timeseries is a separate L-sized refactor on
its own; (b) HTTP latency on every dashboard refresh is undesirable
for live diagnostics; (c) ADR-005 (frontend architecture) defers
analyst tooling to a later concern.

### Rejected: pure `ignore_imports` allowlist (Option A)

Pure paperwork. The allowlist would grow to cover every engine type
the dashboard names, defeating the contract.

## Consequences

### Easier

- **Layering invariant enforced at CI**. New dashboard code that
  reaches past the façade fails the build, same as #300/ADR-008's
  domain-layering contracts.
- **Dashboard is now testable in isolation**. The façade's event
  subscribers and history-dict logic can be unit-tested without
  Streamlit; existing smoke test extended with an end-to-end one-day
  run.
- **Engine refactors are safer**. Renaming an internal class no
  longer threatens dashboard breakage — only the façade's re-export
  needs updating.

### Harder

- **Two surfaces drift apart over time.** The HTTP API
  (`agrogame/api/routes.py`) and the in-process façade
  (`agrogame/api/dashboard_facade.py`) both expose engine state but
  via different shapes. If a third consumer arrives, they have a
  choice; the choice itself becomes a maintenance burden.
- **Façade adds one indirection layer.** Reading
  `dashboard/simulation.py` now requires opening
  `dashboard_facade.py` to see what `DashboardSimulationRun` does.
  Mitigated by the façade's docstring + class-level docstrings.
- **`game_no_api` contract needed `allow_indirect_imports = true`**.
  The lazy `dashboard_main` function in `agrogame/__init__.py`
  references `dashboard.app`, which now points at the façade — making
  every package that does `import agrogame` (e.g. `game.save`
  reading `agrogame.__version__`) a transitive `game → api`
  violator. Direct-only mode catches new direct edges; the
  pre-existing transitive chain is documented in the contract
  comment.

## Alternatives Considered

### Wrapper layer for every engine type

Façade owns `DashboardSoilProfile`, `DashboardWeatherRecord`, etc.,
each forwarding to the engine type. Rejected: 8× the LOC for unclear
benefit; the engine types are stable Pydantic models. Revisit per-type
if churn becomes a problem.

### `agrogame.dashboard.adapters` (subpackage of dashboard)

Same shape, but the façade lives inside `dashboard/`. Rejected
because it positions the wormhole as dashboard-internal rather than
"public engine consumer surface" — future consumers (notebooks, CLI)
would have to either re-implement or import from
`dashboard.adapters`, both ugly.

### Status quo + allowlist

Add `dashboard_isolation` contract with `ignore_imports` listing the
~10 violations. Rejected as paperwork — see Decision section.

## References

- Issue #309 — parent
- Issue #303 — analogous question for `agrogame.api` ↛ domain modules
- ADR-005 — frontend architecture (Godot via HTTP API)
- ADR-008 — import layering decisions / port introduction
- graphify trace (2026-05-06) that surfaced the smell as the highest-
  centrality bridge on the SoilProfile node
