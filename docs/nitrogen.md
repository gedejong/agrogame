Nitrogen module summary

- Core: `NitrogenCycle` processes (mineralization, nitrification, denitrification, uptake)
- Subscribes to water events to move NO3 with drainage
- Emits: `NitrificationOccurred`, `NutrientLeached`

Daily step inputs
- temperature, plant demand, root fractions, optional per-layer pH


