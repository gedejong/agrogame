# Cursor Workspace Instructions

- Keep messages concise; include a brief status update each turn.
- Use small, focused edits; do not reformat unrelated code.
- Prefer Poetry for Python deps and scripts.
- Use gh CLI for PRs and branch context.
- Link Jira issues in commits and PRs (e.g., AGRO-123).

## Working Agreement
- Create a feature branch per Jira issue: feat/AGRO-<id>-<slug>
- Conventional commits: feat, fix, chore, docs, refactor, test
- Open PRs against main; keep PRs small and focused
- Update Jira status and add comments at kickoff and PR open/merge

## Status Update & Summary
- Start turns with a 1–2 sentence status update
- End with a brief high-signal summary of changes or answers

## Code Style
- Clear, descriptive names; early returns; handle edge cases first
- Add concise docstrings for non-trivial functions
- Match existing formatting; avoid unrelated changes

## Tools
- Use Poetry for env mgmt; scripts via `poetry run ...`
- Use gh for PRs: `gh pr create --fill --base main --head <branch>`
- Prefer metric units; sensible decimal precision in CSV outputs

## Spec
- Project spec (Confluence):
  https://data-build-company.atlassian.net/wiki/spaces/\~712020da4bf39b64bd41f6b7a8c0fcf6663b39/pages/307167238/Soil+Plant+Atmosphere+Simulation+Farm+Game
