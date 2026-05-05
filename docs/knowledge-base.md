# Knowledge Base

LLM-navigable index of every documented Python package in AgroGame.
Each entry binds a Python module to its docs page and the references,
classes, events, tests, and ADRs that explain it. Maintained per
[#295](https://github.com/gedejong/agrogame/issues/295).

## How to read

Every page in the table below opens with YAML frontmatter that matches
[`docs/knowledge-base-schema.json`](knowledge-base-schema.json):

```yaml
---
module: agrogame.soil.water
doc_type: module
references: ["FAO-56 (Allen et al. 1998), §3", "DSSAT v4.8 manual ch. 3"]
key_classes: [CascadingBucketWaterModel, SoilWaterBalance, ...]
key_events: [WaterInfiltrated, WaterDrained, ...]
primary_tests: [tests/test_soil_water.py, tests/integration/test_realism.py::test_water_balance]
related_adrs: [ADR-002, ADR-006]
---
```

The check `poetry run python scripts/check_docs_coverage.py` validates
every required package has a page, that the frontmatter parses against
the schema, that `key_classes` are importable, and that each package's
`__init__.py` docstring contains an absolute GitHub URL to its docs.

## Index

### Top-level packages

| Package | Page |
|---------|------|
| `agrogame.api` | [api.md](api.md) |
| `agrogame.atmosphere` | [atmosphere.md](atmosphere.md) |
| `agrogame.events` | [events.md](events.md) |
| `agrogame.game` | [game.md](game.md) |
| `agrogame.plant` | [plant.md](plant.md) |
| `agrogame.sim` | [sim.md](sim.md) |
| `agrogame.soil` | [soil.md](soil.md) |
| `agrogame.weather` | [weather.md](weather.md) |

### Soil sub-packages (seed set)

| Package | Page |
|---------|------|
| `agrogame.soil.water` | [water.md](water.md) |
| `agrogame.soil.nitrogen` | [nitrogen.md](nitrogen.md) |
| `agrogame.soil.canopy` | [canopy.md](canopy.md) |
| `agrogame.soil.phenology` | [phenology.md](phenology.md) |

## Allowlist

The following packages directly under `agrogame/` are intentionally exempt
from the docs-page gate — they are dev/visualization helpers without their
own science surface:

- `agrogame.analysis` — calibration / sensitivity analysis scripts
- `agrogame.config` — configuration loaders
- `agrogame.dashboard` — Streamlit dashboard (optional dep)
- `agrogame.params` — parameter library / Pydantic schemas
- `agrogame.plots` — matplotlib helpers (optional dep)

The allowlist is enforced in
[`scripts/check_docs_coverage.py`](https://github.com/gedejong/agrogame/blob/main/scripts/check_docs_coverage.py)
under `PACKAGE_ALLOWLIST`. Update the constant and rerun the script if a
package should be added or removed.
