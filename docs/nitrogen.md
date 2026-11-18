---
module: agrogame.soil.nitrogen
doc_type: module
references:
  - "DSSAT CENTURY/CERES nitrogen submodels"
  - "Parton et al. 1988 — first-order nitrification kinetics"
  - "FAO-56 — water/nitrogen interaction in canopy stress"
key_classes:
  - NitrogenCycle
  - SoilNitrogenState
  - NitrogenFluxes
key_events:
  - NitrificationOccurred
  - NutrientLeached
  - VolatilizationOccurred
  - MassFlowNSupplyComputed
  - ProtonLoadOccurred
primary_tests:
  - tests/test_soil_nitrogen.py
  - tests/test_nitrogen_volatilization_massflow.py
  - tests/unit/test_proton_budget.py
  - tests/unit/test_nitrification_ph.py
  - tests/integration/test_realism.py
related_adrs: [ADR-002, ADR-006, ADR-013, ADR-020]
---

Nitrogen module summary

- Core: `NitrogenCycle` processes (mineralization, nitrification, denitrification, uptake)
- Subscribes to water events to move NO3 with drainage
- Emits: `MineralizationOccurred`, `NitrificationOccurred`, `DenitrificationOccurred`, `VolatilizationOccurred`, `NutrientLeached`, `MassFlowNSupplyComputed`, `ProtonLoadOccurred`
- Proton budget (#492, ADR-020): each transformation adds its stoichiometric H+ per N to a per-layer budget, released at `DayTick(day_end)` as `ProtonLoadOccurred` (urea hydrolysis at application); soil chemistry turns it into pH through the buffer capacity. See `docs/soil.md`.

Daily step inputs
- temperature, plant demand, root fractions, optional per-layer pH

### Nitrification

`_nitrify_layer` converts NH4 to NO3 at `nitrification_base_rate` (0.15/day, APSIM
SoilN order of magnitude) times these factors, capped at `nitrification_max_rate`
(0.20/day):

- temperature: Q10 = 2 about 20 °C;
- moisture: `(theta / fc)^2`, steeper than mineralisation (Stark & Firestone 1995);
- aeration: `1 - anaerobic fraction` (the gas-diffusion O2 override, else the WFPS proxy);
- pH: `max(0, min(1, 0.33 pH - 1.36))`, 0 at pH 4.12 and 1 from 7.15 (DSSAT-CSM v4.8
  `Soil/Inorganic_N/SOILNI.for`, `PHFACT`; the routine cites Gilmour 1984, SSSAJ
  48:1262-1266). Field data keep nitrification pH-sensitive above 6: ~89 % of
  fall-applied NH3 nitrified by mid-April above pH 7.5, ~39 % below 6.0 (Kyveryga et
  al. 2004, SSSAJ 68:545-551);
- microbial activity: yesterday's `activity_index_excl_ph`, the heterotroph index
  without its pH modifier, so pH enters once (#558, ADR-020);
- fungal dominance: `0.7 + 0.3 (1 - fungal fraction)`.

Nitrification adds 2 mol H+ per mol N to the proton budget (ADR-020).

### NH3 volatilisation

Uptake and nitrification remove the exposed-fertiliser tag in proportion to
NH4 removed from the mixed surface pool. Complete removal clears the tag
before mineralisation or another application can replenish NH4. Subsoil
removal leaves the surface tag unchanged.

Only the surface layer volatilises. Surface-applied urea hydrolyses in a band whose pH
rises to about 9, where roughly a third of the ammoniacal N is dissolved NH3.
`SoilNitrogenState.surface_fertilizer_nh4_kg_ha` tracks that exposed share of the
layer-0 NH4; it loses `volatilization_base_rate` (5 %/day at 20 °C, Q10 = 2, capped at
`volatilization_max_rate`) until dissolution, rain and diffusion incorporate it at
`fertilizer_incorporation_rate_per_day` (15 %/day). The cumulative loss from a surface
urea dressing is therefore ~25 % of the applied N, inside the 10–30 % field range
(Bouwman, Boumans & Batjes 2002, Global Biogeochem. Cycles 16: 1024). Native and
incorporated NH4 sits at the bulk soil pH, where the NH3 fraction is ~1 % of the band
value (Henderson–Hasselbalch, pKa 9.25), and loses that fraction of the base rate: a few
kg N/ha per season at most on unfertilised soil (Sommer, Schjoerring & Denmead 2004,
Adv. Agron. 82). `apply_urea` on layer 0 feeds the exposed pool; deeper placements and
`apply_ammonium_nitrate` (an acid-forming salt, 1–3 % field loss) do not. The exposed
pool is part of the soil snapshot.

### Mass flow

`TranspirationByLayer` triggers a per-layer estimate of the nitrate the transpiration
stream could carry to the roots (layer NO3 concentration × water extracted, bounded by
the pool). It is published as `MassFlowNSupplyComputed(total_kg_ha, by_layer)` and
exposed as `NitrogenCycle.massflow_supply_kg_ha`; it debits nothing. Plant uptake in
`daily_step` is demand-driven and capped by the mineral N in each rooted layer
(ADR-013), so the mass-flow figure says whether convection alone could meet the crop's
demand or diffusion must contribute.

### Stress signal

After daily uptake, a nutrient stress factor `stress_N = uptake/demand` (clamped to [0, 1]) is emitted via `NutrientStressComputed(nutrient="N")`.

