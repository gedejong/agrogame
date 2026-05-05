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
primary_tests:
  - tests/test_nitrogen.py
  - tests/integration/test_realism.py
related_adrs: [ADR-002, ADR-006]
---

Nitrogen module summary

- Core: `NitrogenCycle` processes (mineralization, nitrification, denitrification, uptake)
- Subscribes to water events to move NO3 with drainage
- Emits: `MineralizationOccurred`, `NitrificationOccurred`, `DenitrificationOccurred`, `VolatilizationOccurred`, `NutrientLeached`

Daily step inputs
- temperature, plant demand, root fractions, optional per-layer pH

### Stress signal

After daily uptake, a nutrient stress factor `stress_N = uptake/demand` (clamped to [0, 1]) is emitted via `NutrientStressComputed(nutrient="N")`.

