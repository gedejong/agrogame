## Phosphorus cycle and pH effects

This module models phosphorus (P) dynamics per soil layer and integrates with the event system and the full orchestrator.

- **Pools**: `organic_p`, `available_p`, `fixed_p`. Mass is conserved across pools and pending fertilizer releases.
- **Mineralization (temperature + moisture)**: Organic → available. We use a mid-range daily rate derived from 0.5–2%/month at 25°C and apply a Q10-like temperature factor: doubling per +10°C from 25°C, and a moisture scaling by `theta / field_capacity` clamped to [0.3, 1.0].
- **pH availability**: Uptake uses a piecewise-linear availability modifier anchored at pH 4–9 with optimum near 6.5–7.0.
- **Fixation**: Moves `available_p` → `fixed_p`. Daily rate derived from weekly 1–5%, scaled higher under acidic pH. Emits `PhosphorusFixationOccurred`.
- **Uptake**: Allocated by root fractions per layer. Effective uptake is reduced by the pH availability modifier.
- **Slow-release fertilizer**: `apply_slow_release_p(layer, amount, release_days)` applies 20% immediately and schedules the remainder evenly across `release_days`, releasing each day before transformations. Scheduled remainder is included in mass-balance accounting.
- **Water-driven movement**: P is largely immobile. Under very heavy drainage, a tiny fraction of `available_p` is lost as `NutrientLeached(nutrient="P")`.

### Events
- Emits: `PhosphorusFixationOccurred`, `NutrientLeached(nutrient="P")`
- Consumes: `RootDistributionUpdated`, `SoilPHUpdated`, `WaterDrained`

### Visualization
Time-series scripts include profile-sum P pools and P-stress in the full integration plot. pH over time is plotted from the Chemistry module.

### Notes and assumptions
- Parameters are intentionally simple and documented in code constants. Replace with calibrated process rates as data becomes available.

