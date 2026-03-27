Nitrogen module summary

- Core: `NitrogenCycle` processes (mineralization, nitrification, denitrification, uptake)
- Subscribes to water events to move NO3 with drainage
- Emits: `MineralizationOccurred`, `NitrificationOccurred`, `DenitrificationOccurred`, `VolatilizationOccurred`, `NutrientLeached`

Daily step inputs
- temperature, plant demand, root fractions, optional per-layer pH

### Stress signal

After daily uptake, a nutrient stress factor `stress_N = uptake/demand` (clamped to [0, 1]) is emitted via `NutrientStressComputed(nutrient="N")`.

