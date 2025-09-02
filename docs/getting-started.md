# Getting Started

```bash
poetry install --with dev
poetry run simulate
```

## Soil presets

Presets for common soil textures and regional variants are provided in `data/soils/presets.yaml`.

- Load and validate:
```bash
poetry run python -c "from agrogame.soil.loader import load_soil_presets; import pathlib; print(load_soil_presets(pathlib.Path('data/soils/presets.yaml')).model_dump_json()[:120] + '...')"
poetry run python scripts/validate_soils.py
```

These ranges are heuristic and aligned with the high-level design (see Confluence). For scientific calibration, compare against ISRIC SoilGrids for your region.

## Water model abstraction

The soil water balance uses a small interface to keep models swappable. Start with the default cascading bucket model.
See [Water Model Abstraction](architecture/water_model_abstraction.md) for details.
