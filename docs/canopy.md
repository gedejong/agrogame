---
module: agrogame.soil.canopy
doc_type: module
references:
  - "Beer–Lambert canopy light interception (Monsi & Saeki 1953)"
  - "WOFOST/SUCROS RUE-based biomass accumulation"
  - "DSSAT phenology-coupled senescence"
key_classes:
  - CanopyModule
  - CanopyParams
  - CanopyState
  - CanopyFluxes
key_events:
  - LightIntercepted
  - BiomassAccumulated
  - LAIUpdated
  - CanopyIntercepted
  - CanopyEvaporated
  - GrainNumberSet
primary_tests:
  - tests/test_canopy.py
  - tests/integration/test_realism.py
related_adrs: [ADR-002]
---

Canopy summary

- Interception: Beer–Lambert `fraction = 1 - exp(-k * LAI)`
- Biomass: `biomass = intercepted_PAR * RUE * temp_factor * min(water, N)`
- LAI: `ΔLAI = SLA * new_leaf_biomass * (1 - LAI/LAImax) - LAI * sen_rate`
- Phenology: higher senescence in grain fill
- Events: `LightIntercepted`, `BiomassAccumulated`, `LAIUpdated`

### Stress integration

Biomass growth scales by `min(water_stress, n_stress)`. Water stress is derived from ET supply/demand via a `WaterStressComputed` event. Nutrient stress is proxied from N/P uptake vs demand via `NutrientStressComputed`. These are combined (default Liebig minimum) and applied to growth and partitioning, with heightened sensitivity during flowering and grain fill.

### Grain sink-source model (#321)

Grain is no longer a fixed harvest-index fraction of daily biomass. When a
crop preset sets `grains_per_g_source > 0`, the canopy uses a two-stage
CERES-style model so harvest index becomes an *emergent*, bounded outcome:

1. **Grain number (floret fertility).** Entering `GRAIN_FILL` snapshots
   canopy biomass. Over a peri-anthesis critical window
   (`grain_set_window_gdd`), potential grain number is set to
   `grains_per_g_source * (biomass growth in the window)`, then frozen and
   announced via `GrainNumberSet`. Because that window growth already
   integrates temperature (cold), water and N stress through the RUE source
   term, all three stresses in the window lower grain number (Andrade et al.
   1999; Fischer 1985; DSSAT CERES `G1`).
2. **Grain filling (kernel weight).** Each day a fill *demand* =
   `grain_number * kernel_fill_rate_mg_per_grain_day` (heat-scaled, bounded
   by the remaining total sink `grain_number * potential_kernel_weight_mg`,
   CERES `G2`) is met from current assimilate first, then from remobilised
   stem (`remobilization_fraction`) and senescing-leaf
   (`leaf_remob_fraction`) reserves (Gebbing & Schnyder 1999). Post-anthesis
   heat/drought reduce the fill rate and source, so realised kernel weight
   (`grain / grain_number`) drops.
3. **Emergent, bounded HI.** Cumulative grain is capped at
   `hi_max * total_biomass` (safety ceiling ~0.50-0.55 for cereals). Grain
   number, not the cap, is the dominant yield lever in unstressed runs.

Remobilisation and the cap are internal transfers, so total biomass is
unchanged. `grains_per_g_source == 0` (grape, un-migrated presets) keeps the
legacy fixed-`harvest_index` allocation. State (`grain_number`) resets on
`Harvested` and round-trips through `to_dict`/`from_dict`.

### Rainfall interception

Capacity per day: `C = capacity_coef_mm_per_lai * LAI` (mm). The canopy stores intercepted water up to remaining capacity; any excess becomes throughfall. During the daily ET step, canopy evaporation is prioritized before soil evaporation.

Sequencing in a day:

1) Interception: `(intercepted, throughfall) = intercept(LAI, rainfall)`
2) Soil water update with `throughfall` and evaporation driver set to 0
3) Potential ET split into evaporation/transpiration; canopy `evaporate(potential_evap)` reduces soil evaporation by the amount taken from the canopy store

Events:
- `CanopyIntercepted(amount_mm)` emitted when interception occurs
- `CanopyEvaporated(amount_mm)` emitted when canopy evaporation reduces the store


