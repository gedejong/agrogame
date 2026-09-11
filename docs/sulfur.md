---
module: agrogame.soil.sulfur
doc_type: module
references:
  - "Eriksen 2009 — Adv. Agron. 102: soil sulfur cycling; net field S mineralisation 5–20 kg S/ha/yr"
  - "Scherer 2001 — Eur. J. Agron. 14: sulphur in crop production"
  - "Chao, Harward & Fang 1962 — Soil Sci. Soc. Am. Proc. 26: sulfate adsorption and desorption in soils"
  - "Curtin & Syers 1990 — J. Soil Sci. 41: mechanism of sulphate adsorption by two soils"
  - "Selim 1992 — Adv. Agron. 47: two-site sorption kinetics for inorganic solutes"
  - "Jury & Horton 2004 — Soil Physics: retardation of sorbing solutes"
key_classes:
  - SulfurCycle
  - SoilSulfurState
  - SulfurRateParams
key_events:
  - SulfurMineralized
  - SulfurAdsorbed
  - NutrientLeached
  - NutrientStressComputed
primary_tests:
  - tests/test_sulfur.py
  - tests/test_sulfur_growth_stress.py
  - tests/integration/test_realism.py
related_adrs: [ADR-002, ADR-010]
---

## Sulfur cycle

`agrogame.soil.sulfur` models sulfur (S) per soil layer without a redox
pathway: organic S mineralises to sulfate, sulfate exchanges reversibly with
sorption sites, moves with drainage and is taken up by roots. The module has
the same shape as the phosphorus module: `SulfurCycle` holds the processes,
`SoilSulfurState` the pools, `SulfurRateParams` the frozen rate constants and
`SulfurRuntime` the event wiring.

### Pools (kg S/ha per layer)

- **`organic_s`** — S bound in soil organic matter, seeded from the layer's
  organic-matter mass at 0.8 % S (`ORGANIC_MATTER_S_FRACTION`); a 3 % OM
  profile carries roughly 2,000 kg S/ha.
- **`available_s`** — dissolved sulfate-S, seeded
  from `initial_s_kg_ha` in the soil preset.
- **`adsorbed_s`** — sulfate held reversibly on Fe/Al-oxide and clay-edge
  sites. It starts in kinetic equilibrium with the available pool (see
  below) rather than empty.

All three pools plus scheduled fertiliser releases are conserved;
`total_sulfur_kg_ha()` sums them.

### Processes

- **Mineralisation** (organic → available). The daily base rate is the
  mid-point of the monthly bounds in `SulfurRateParams` divided by 30 at the
  25 °C reference, doubled per +10 °C (Q10 = 2), scaled by moisture
  (`theta / field_capacity` clamped to 0.3–1.0) and by the microbial
  activity index. The bounds are calibrated so a temperate season sums to the
  5–20 kg S/ha/yr field band (Eriksen 2009). Emits `SulfurMineralized`.
- **Adsorption and desorption** (available ⇄ adsorbed). The weekly
  adsorption fraction rises linearly with an acidity index (0 at pH ≥ 7, 1 at
  pH ≤ 4) and is multiplied by a reference-normalised clay response (1.0 at
  22 % clay, the loam reference, clamped to 0.3–3.0). Desorption releases a
  fixed weekly fraction of the adsorbed pool. Both run daily at one seventh
  of the weekly fraction; the net exchange is emitted as `SulfurAdsorbed`.
  These relations live in `agrogame.soil.sulfur.sorption` and are shared by
  the initial state and the daily exchange.
- **Initial equilibrium.** A field soil has equilibrated its sorbed and
  dissolved sulfate over years, so `SoilSulfurState` sizes the adsorbed pool
  at the fast-exchange equilibrium of the two rate constants,
  `available × adsorption_weekly(pH, clay) / desorption_weekly`, evaluated at
  the default pH of 6.8 (the ratio of the two rate constants is the
  fast-site partition of a two-site sorption model, Selim 1992). On the loam
  reference this is 0.38 × the available pool; an empty sorbed pool would
  instead turn the first weeks of a season into a net sulfate sink.
- **Uptake and stress.** Plant demand is allocated to layers by root
  fraction and reduced by a piecewise-linear pH availability modifier
  (anchors between pH 4 and 9, optimum near neutral). `SulfurRuntime` turns
  uptake / demand into `NutrientStressComputed(nutrient="S")` through the
  Liebig stress calculator; demand comes from `DayTick.plant_s_demand_kg_ha`
  (0.05 kg/ha/d when the tick carries none).
- **Leaching.** On `WaterDrained`, dissolved sulfate follows the water:

      moved_kg_ha = available_s × clamp(drainage_mm / storage_mm, 0, 1)

  The adsorbed pool stays in the layer until daily desorption releases it.
  This explicit exchange supplies retention; applying an equilibrium
  retardation factor to the dissolved pool would count that retention twice.
  For example, 20 kg S/ha in 120 mm of water carries 0.1667 kg S/ha in a
  1 mm drainage pulse. Internal drainage credits the next layer; drainage
  outside the profile emits `NutrientLeached(nutrient="SO4")`.
- **Fertilisers.** `apply_gypsum` adds soluble sulfate at once;
  `apply_elemental_s` releases a small share immediately and schedules the
  rest evenly over its oxidation window, released each day before the
  transformations.
- **Soil temperature.** The runtime uses the daily mean of the tick's
  `tmin_c` and `tmax_c` as the soil-temperature proxy, the same proxy the gas
  and nitrogen runtimes use, so mineralisation follows the climate; a tick
  without temperatures uses 18 °C.

### Events

- Emits: `SulfurMineralized`, `SulfurAdsorbed`, `NutrientLeached(nutrient="SO4")`,
  `NutrientStressComputed(nutrient="S")`
- Consumes: `DayTick` (nutrients phase), `WaterDrained`, and through the
  shared `EnvironmentalCache` the per-layer pH, root-fraction and microbial
  activity updates

### Notes and assumptions

- Non-redox by design: there is no sulfate reduction or sulfide pathway
  under anoxia.
- Every layer is at pH 6.8 until the chemistry module reports per-layer
  values; the initial adsorbed pool is sized at that pH.
- Sorption is linear with no capacity limit. Its kinetic rates depend on
  clay and acidity and are not calibrated individually for each soil preset.
