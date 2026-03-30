# AgroGame — Claude Code Project Instructions

Soil-plant-atmosphere simulation engine powering an isometric farming game.
Backend in Python (science, game logic, REST API); frontend in Godot 4 (GDScript).

## Architecture Decisions

Key design choices are recorded in `docs/adr/`:

- [ADR-001](docs/adr/ADR-001-game-state-persistence.md) — Game state format and persistence
- [ADR-002](docs/adr/ADR-002-multi-field-architecture.md) — Multi-field architecture (Field → Patch → Orchestrator)
- [ADR-003](docs/adr/ADR-003-economic-model.md) — Economic model scope (credits, price table, ledger)
- [ADR-004](docs/adr/ADR-004-game-loop-turn-system.md) — Game loop and turn system (season phases, pause events)
- [ADR-005](docs/adr/ADR-005-frontend-architecture.md) — Frontend: Godot 4, GDScript, "Monument Valley meets agricultural textbook"
- [ADR-006](docs/adr/ADR-006-performance-strategy.md) — Performance: NumPy → Numba → Cython path

Read relevant ADRs before working on related code. Propose a new ADR for significant architectural changes.

## Repository Structure

```
agrogame/          # Python — simulation engine, game logic, API
  sim/             #   Orchestrator, day-tick phases
  soil/            #   Water balance, nitrogen cycle, SOM (3-pool RothC)
  plant/           #   Phenology, canopy, roots, crop presets
  weather/         #   Climate drivers, presets
  atmosphere/      #   ET (Penman-Monteith)
  game/            #   EconomicLedger, FieldManager, GameTurnManager
  api/             #   FastAPI REST API (POST /games, /start-season, etc.)
  events/          #   EventBus, BaseEvent
  dashboard/       #   Streamlit/Plotly (optional extras)
game/              # Godot 4 — frontend
  scripts/         #   GDScript sources (farm_view, api_client, camera, weather)
  scenes/          #   .tscn scene files
  assets/          #   SVG tiles, crop sprites
  tests/           #   GUT unit tests
  addons/          #   GUT test framework
docs/              # MkDocs documentation, ADRs
tests/             # Python test suite (pytest)
data/              # YAML presets (crops, climate, economy, soil)
scripts/           # Utility scripts (plots, analysis)
```

## Working Agreement

- Feature branch per Jira issue: `feat/AGRO-<id>-<kebab-summary>`
- Conventional commits: feat, fix, chore, docs, refactor, test
- Link Jira issue key in commits and PR titles (e.g., AGRO-123)
- Open PRs against `develop`; keep PRs small and focused
- Update Jira status and add comments at kickoff and PR open/merge
- Only ask questions when information is missing or ambiguous

## Code Style (Python)

- Write readable, explicit code; annotate public APIs with type hints
- Prefer meaningful names; early returns; handle edge cases first
- Add concise docstrings for non-trivial functions only
- Keep functions focused; avoid deep nesting
- No import-time side effects; guard optional deps with local imports
- Match existing formatting; avoid unrelated changes
- Enforce with: ruff, flake8, black, mypy, xenon, deptry, importlinter

## Code Style (GDScript)

- Target Godot 4.6+; use static typing on all variables and return types
- Explicit types on `min()`/`max()`/Variant-returning builtins (e.g., `var x: float = min(a, b)`)
- Prefix private members with `_`; use `@onready` for node refs
- Enforce with: gdlint, gdformat (via gdtoolkit)
- 100% file-level test coverage enforced by `game/tests/check_coverage.sh`
- Tests use GUT framework (`extends GutTest`)

## Defensive Coding

- Validate inputs at module boundaries and public APIs
- Never `except Exception: pass` — catch specific exceptions, log and re-raise
- Keep `try/except` scopes small
- Use `raise ValueError` for runtime invariants (not `assert`)
- Prefer early returns and guard clauses over deep nesting
- Event handlers: minimal payloads, validated types, fast execution

## Event System

- Use `agrogame.events.EventBus` and `BaseEvent` across modules
- Handlers must be fast; avoid cross-module state mutation
- Prefer module-local events; keep contracts stable and documented
- All events are debug-logged at emit

## Simulation

- Equations from literature (DSSAT, APSIM, WOFOST, FAO-56); cite source in comments
- Parameters in frozen `*Params` dataclasses; mutable state in `*State` dataclasses
- Crop/climate presets in `data/` YAML files, loaded via `CropLibrary.get_preset(crop_key, climate_key)`
- Realism tests in `tests/integration/test_realism.py` — check against literature ranges

## API

- FastAPI app in `agrogame/api/`, served with `make serve-api` (requires `poetry install -E api`)
- In-memory game sessions; Pydantic request/response models
- Godot frontend communicates via HTTP to `localhost:8000/api/v1/`

## Dashboard (Streamlit/Plotly)

- Keep dashboard imports optional; import heavy deps locally
- High-contrast toggle, informative tooltips, responsive layout
- Add smoke tests that import the module; skip when extras missing

## Tests & CI

- Python: run locally before pushing — black, ruff, flake8, mypy, pytest with coverage
- Python coverage threshold ~97%; enforced by CI
- GDScript: gdlint, gdformat, GUT tests, 100% file coverage
- GitHub Actions: ubuntu-latest, Python 3.10 on PRs; full matrix on releases
- Skip optional-extras tests when deps absent (e.g., streamlit/plotly)
- Use `pytest-xdist` for parallel test execution

## Tools

- Use Poetry for dependency and environment management (`poetry run ...`)
- Optional extras: `poetry install -E api` (fastapi/uvicorn), `-E dashboard` (streamlit/plotly)
- Use `gh` CLI for PRs: `gh pr create --base develop`
- Prefer metric units; sensible decimal precision in outputs

## Documentation

- Concise, high-signal docs in `docs/` per module
- Update MkDocs navigation (`mkdocs.yml`) when adding docs
- ADRs in `docs/adr/` for significant architectural decisions

## Jira Workflow

1. Fetch acceptance criteria from Jira story
2. Post brief implementation plan as Jira comment
3. Transition to In Progress with branch name
4. Implement step-by-step
5. Run pre-commit hooks locally
6. Open PR with checklist of acceptance criteria
7. After merge: pick next highest-priority Jira story

## Project Spec

- Confluence: https://data-build-company.atlassian.net/wiki/spaces/~712020da4bf39b64bd41f6b7a8c0fcf6663b39/pages/307167238/Soil+Plant+Atmosphere+Simulation+Farm+Game
