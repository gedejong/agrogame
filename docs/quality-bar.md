# AgroGame Quality Bar

Source of truth for every enforced gate on the project. If a gate isn't
listed here, it isn't enforced. If a gate **is** listed here, breaking it
should fail CI on a PR. Updated as part of #297 (Phase 4 of #293).

## Enforced gates (PR-blocking)

| Gate | Tool | Configuration | Owner of failure messages |
|------|------|---------------|---------------------------|
| Formatting | `black` | `[tool.black]` (line-length 88, py310) | pre-commit + CI |
| General lint | `ruff` | `[tool.ruff.lint]` `select = E, F, B, C4, RUF, UP` | pre-commit + CI |
| Pydocstyle (pilot) | `ruff --select D` | Pilot packages: `agrogame/soil/water`, `agrogame/events` | pre-commit + CI |
| Style/docstring conv. | `flake8` | `pyproject.toml` `[tool.flake8]` | pre-commit + CI |
| Type check (project-wide) | `mypy` | `[tool.mypy]` (no_implicit_optional, warn_*) | CI + pre-commit (manual) |
| Type check (strict pilot) | `mypy --strict` | Pilot package: `agrogame/events` | CI + pre-commit (manual) |
| Cyclomatic complexity | `xenon` | B/B/C (`--max-average B --max-modules B --max-absolute C`) | CI + pre-commit (manual) |
| Import contracts | `import-linter` | `.importlinter` — all 10 contracts (see [Import-linter contracts](#import-linter-contracts)) | CI + pre-commit (manual) |
| Test suite | `pytest --cov` | Coverage floor 92% (`pyproject.toml` `[tool.pytest.ini_options]`) | CI + pre-commit (manual) |
| Realism (literature) | `pytest tests/integration/test_realism.py` | Literature-cited ranges per assertion | CI |
| Dead code | `vulture` (#297) | `--min-confidence 80` against `vulture-whitelist.py` | CI + pre-commit (manual) |
| Dependency hygiene | `deptry` | `[tool.deptry]` allowlist | CI |
| KB ↔ package binding | `scripts/check_docs_coverage.py` | Allowlist in script + `docs/knowledge-base-schema.json` | CI + pre-commit (manual) |
| Canonical class docstrings | `scripts/check_class_docstrings.py` | 100% on `*Params`/`*State`/`*Module`/`*Runtime` | CI + pre-commit (manual) |
| Internal-link integrity | `scripts/check_docs_coverage.py` | Bundled with KB check | CI + pre-commit (manual) |
| ADR section presence | `scripts/check_docs_coverage.py` | Status/Context/Decision/Consequences | CI + pre-commit (manual) |
| Docstring coverage | `interrogate` | `[tool.interrogate]` floor 50% (ratchet, target 90%) | CI + pre-commit (manual) |
| Docs build | `mkdocs build --strict` | `mkdocs.yml` | CI |
| GDScript lint | `gdlint` | `gdtoolkit` defaults | pre-commit + CI |
| GDScript format | `gdformat --check` | `gdtoolkit` defaults | pre-commit + CI |
| GDScript test coverage | `game/tests/check_coverage.sh 100` | 100% file coverage | pre-commit + CI |

## Mypy strictness roadmap

We promote one package at a time to `mypy --strict`. The promotion order is
chosen to surface real type debt without bundling a refactor with the
strict-mode gate.

| Package | Status | Notes |
|---------|--------|-------|
| `agrogame.events` | ✅ Strict (#297) | Small surface, no domain logic |
| `agrogame.weather` | Pending | Pure data + utilities; small effort |
| `agrogame.atmosphere` | Pending | Single sub-package (`et`); fewer cross-imports |
| `agrogame.sim` | Pending | Composition root — strictness here forces correct typing on every domain runtime |
| `agrogame.soil.*` | Pending | Subpackage-by-subpackage |
| `agrogame.plant.*` | Pending | After soil |
| `agrogame.api` | Pending | FastAPI / Pydantic interplay needs care |
| `agrogame.game` | Pending | Last; depends on the rest |

Strict typing is enforced via a separate CI invocation (`poetry run mypy
--strict agrogame/<pkg>`) rather than `[[tool.mypy.overrides]]` because the
override form caused strict flags to leak into transitive importers in
mypy 1.19.

## Interrogate ratchet

Phase 3 (#296) prescribed a 90% project-wide docstring-coverage target. The
current measured baseline (after the canonical-class fill) is **54.1%**.
The configured floor in `[tool.interrogate]` is **50%** as a ratchet — each
PR that lifts coverage by ≥ 5 percentage points should bump the floor by
the same amount. The 100% gate on `*Params`/`*State`/`*Module`/`*Runtime`
classes is enforced separately by `scripts/check_class_docstrings.py`.

Tracking issue for the ratchet: a follow-up to #296 (TBD).

## Import-linter contracts

All 10 contracts pass. `lint-imports` runs without `--contract` filters in
both pre-commit (manual stage) and the Quality CI job. See
[`docs/adr/ADR-008-import-layering.md`](adr/ADR-008-import-layering.md)
for the layering decision and the rationale behind each contract's
`ignore_imports` allowlist.

| Contract | Notes |
|----------|-------|
| `events_isolated` | `agrogame.events` is type-only; no domain imports. |
| `soil_plant_direction` | Allowlist for soil → plant.events subscriptions. |
| `weather_independence` | Weather is the foundational layer. |
| `atmosphere_independence` | ET runtime uses `atmosphere/et/ports.py` Protocols (#300). |
| `plant_independence` | Plant doesn't depend on atmosphere. |
| `sim_isolation` | `DayTick` lives at `agrogame.events.calendar` (#300). |
| `soil_subdomain_independence` | Allowlist for canopy↔phenology + nitrogen↔water events. |
| `plant_vs_soil` | Allowlist for plant.roots.runtime → soil.phenology runtime read. |
| `domain_layers` | atmosphere > plant > soil > weather; allowlist mirrors `soil_plant_direction`. |
| `game_no_api` | Game layer doesn't depend on the API layer. |

## Docstring conventions

- Every public `*Params`, `*State`, `*Module`, `*Runtime` class must
  carry a docstring (enforced by `scripts/check_class_docstrings.py`).
- Every package directly under `agrogame/` (minus the allowlist in
  `scripts/check_docs_coverage.py`) must have a `docs/<page>.md` with
  KB frontmatter binding it to the module.
- Each required package's `__init__.py` first paragraph must contain
  the absolute GitHub URL to its docs page.
- New ADRs use `docs/adr/_template.md`; the four required sections
  (Status, Context, Decision, Consequences) are checked.
- Pydocstyle (`ruff D`) is enforced on the pilot packages
  (`agrogame/soil/water`, `agrogame/events`); rollout continues
  package-by-package.

## How to run locally

```bash
poetry install --with dev

# Project-wide
poetry run black --check .
poetry run ruff check .
poetry run flake8
poetry run mypy agrogame
poetry run mypy --strict agrogame/events

# Quality (heavy; CI mirror)
poetry run xenon --max-average B --max-modules B --max-absolute C \
    --ignore 'tests/*,docs/*,out/*' --exclude 'agrogame/plots/*' agrogame
poetry run lint-imports --config .importlinter
poetry run vulture agrogame vulture-whitelist.py --min-confidence 80
poetry run deptry agrogame
poetry run pytest --cov

# Documentation
poetry run mkdocs build --strict
poetry run python scripts/check_docs_coverage.py
poetry run python scripts/check_class_docstrings.py
poetry run interrogate agrogame
```

Run all heavy gates at once:

```bash
poetry run pre-commit run --hook-stage manual --all-files
```

## Adding a new gate

1. Wire the gate in `.github/workflows/quality.yml` (or `python.yml` for
   project-wide concerns).
2. Add a manual-stage hook in `.pre-commit-config.yaml` so contributors can
   run it locally before pushing.
3. Update this page — both the table above and the local-run snippet.
4. Open a follow-up if the new gate is started in ratchet mode (interrogate
   floor, ruff `D` rollout) so the ratchet is tracked separately.
