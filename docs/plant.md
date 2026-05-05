---
module: agrogame.plant
doc_type: module
references:
  - "WOFOST/SUCROS — RUE-driven biomass partitioning"
  - "DSSAT — root depth and water-uptake submodels"
key_classes: []
key_events: []
primary_tests:
  - tests/test_root_module.py
  - tests/test_biomass.py
related_adrs: [ADR-002]
---

# Plant

Plant-side modules that don't live under `agrogame.soil`. Today this covers
biomass partitioning and root growth/water-uptake; canopy and phenology
currently sit under `agrogame.soil` (canopy/phenology) for legacy reasons —
relocation is tracked in audit umbrella **#280**.

## Submodules

- `agrogame.plant.biomass` — `BiomassState`, biomass partitioning helpers.
- `agrogame.plant.roots` — root depth and per-layer root fraction module.
- `agrogame.plant.presets` — `CropLibrary.get_preset(crop, climate)` loader
  for `data/crops/presets.yaml`.

## Related

- [Canopy](canopy.md) — `agrogame.soil.canopy`
- [Phenology](phenology.md) — `agrogame.soil.phenology`
