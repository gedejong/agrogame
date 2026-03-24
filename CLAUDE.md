# AgroGame — Claude Code Project Instructions

Soil-plant-atmosphere simulation engine for farming game.

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

## Defensive Coding

- Validate inputs at module boundaries and public APIs
- Never `except Exception: pass` — catch specific exceptions, log and re-raise
- Keep `try/except` scopes small
- Use assertions for internal invariants only (not runtime errors)
- Prefer early returns and guard clauses over deep nesting
- Event handlers: minimal payloads, validated types, fast execution
- Plotting/CLI: validate file paths, create parents deliberately

## Event System

- Use `agrogame.events.EventBus` and `BaseEvent` across modules
- Handlers must be fast; avoid cross-module state mutation
- Prefer module-local events; keep contracts stable and documented
- All events are debug-logged at emit

## Dashboard (Streamlit/Plotly)

- Keep dashboard imports optional; import heavy deps locally
- High-contrast toggle, informative tooltips, responsive layout
- Provide CSV exports; PNG export optional via kaleido
- Add smoke tests that import the module; skip when extras missing

## Tests & CI

- Run locally before pushing: black, ruff, flake8, mypy, pytest with coverage
- Coverage threshold enforced by CI — keep tests at or above configured value
- GitHub Actions: ubuntu-latest, Python 3.10 on PRs; full matrix on releases
- Skip optional-extras tests when deps absent (e.g., streamlit/plotly)
- Investigate xenon/importlinter/deptry failures locally

## Tools

- Use Poetry for dependency and environment management (`poetry run ...`)
- Use `gh` CLI for PRs: `gh pr create --fill --base main --head <branch>`
- Prefer metric units; sensible decimal precision in CSV outputs

## Documentation

- Concise, high-signal docs in `docs/` per module
- Update MkDocs navigation (`mkdocs.yml`) when adding docs
- Use equations/links where helpful

## Repository Structure

- Key directories: `agrogame/` (modules), `docs/` (MkDocs), `scripts/`, `tests/`, `data/`
- Code owner: edwin.dejong@databuildcompany.com

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
