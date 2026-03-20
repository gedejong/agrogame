# AgroGame Quality Standards

## Complexity
- Target McCabe complexity ≤ 10 per function
- Xenon gates:
  - Average ≤ B
  - Worst module ≤ B
  - Absolute cap: C

## Architecture
- All imports must satisfy `.importlinter` contracts
- Prefer dependency inversion or ports/adapters if rules block changes

## Dependencies
- Additions require:
  1. Update to `pyproject.toml`
  2. Passing `deptry` check
  3. Brief justification in PR

## Dead Code
- Remove unused code or whitelist with justification in review

## How to run locally
```bash
poetry install --with dev
poetry run importlinter --path . --config .importlinter
poetry run xenon --max-average B --max-modules B --max-absolute C --ignore tests/*,docs/*,out/* agrogame
poetry run deptry . --exclude tests,docs,build,dist,out
poetry run vulture agrogame --min-confidence 80
```

## CI Parity
- Pre-commit mirrors CI checks
- Baseline metrics can be saved to `out/` for trend tracking

