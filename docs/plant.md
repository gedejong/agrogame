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
related_adrs: [ADR-002, ADR-013]
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

## Roots after maturity

The root front stops at physiological maturity (#539).
`RootModule._stage_multiplier` returns 0.0 at MATURITY, ahead of any crop
override in `RootParams.stage_multipliers`, so the depth and the per-layer
root fractions hold their maturity values. This follows CERES-Maize, where the
front advances only on days with new root growth (DSSAT-CSM `MZ_ROOTS.for`;
Jones et al. 2003), APSIM Next Generation, whose `RootFrontVelocity` is 0 by
maturity (Holzworth et al. 2014), and WOFOST, which stops the front once root
partitioning reaches 0 (de Wit et al. 2019). APSIM and WOFOST stop it earlier,
around anthesis; aligning the pre-maturity stage table is a calibration
question outside #539.

Root turnover continues at `turnover_rate_per_day` while the crop stands, as
in APSIM's daily root senescence, and still emits `RootTurnoverOccurred`.
N, P, S and micronutrient uptake stop at maturity as well
([ADR-013](adr/ADR-013-plant-nitrogen-stock.md), amendment 2026-11-24).
Water uptake stops too, through the canopy: a determinate crop has no green
leaf from its first MATURITY step, so it transpires nothing while it stands;
grape keeps its leaves until leaf drop (#623, ADR-013 amendment 2026-11-25,
[Canopy](canopy.md)).

## Related

- [Canopy](canopy.md) — `agrogame.soil.canopy`
- [Phenology](phenology.md) — `agrogame.soil.phenology`
