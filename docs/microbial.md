### Microbial biomass and enzyme activity (AGRO-78)

This module simulates microbial biomass dynamics with environmental controls and enzyme production, and exposes depth-resolved diagnostics for visualization and coupling with nutrient cycles.

- Events: `MicrobialGrowth`, `MicrobialMortality`, `EnzymeProduced`, `EnzymeGroupTotals`, `MicrobialActivityComputed`, `MicrobialFBUpdated`, `SubstrateAvailable`, `RhizospherePrimingPulse`.
- Core: `MicrobialBiomassModule` integrates temperature, WFPS, and pH response modifiers via `EnvironmentalResponses` and computes growth/turnover per soil layer each day.
- Kinetics: Monod substrate limitation is applied to growth, with an enzyme production cost fraction. A rhizosphere priming multiplier scales activity transiently.
- Coupling: Nitrogen/Phosphorus cycles subscribe to `MicrobialActivityComputed` and `MicrobialFBUpdated` to modulate mineralization and nitrification/uptake.
- Orchestration: `MicrobesRuntime` runs on the `nutrients` phase of the daily calendar and aggregates enzyme totals by group.

#### Visualizations

- Timeseries: total microbial C/N and enzyme group costs.
- Depth heatmaps: microbial C, N, fungal vs. bacterial split, enzyme cost, and activity index.
- Dashboard: interactive plot tabs for biomass, enzyme costs, and activity by layer.

Diagnostics:

- Substrate, WFPS, pH depth diagnostics: `out/microbes_diagnostics.png`.
- Activity response surface (T x WFPS at pH 6.8): `out/microbes_activity_surface.png`.

To reproduce images:

```bash
poetry run python scripts/plot_microbes_suite.py --profile loam_temperate --days 120 --out-dir out
poetry run python scripts/plot_full_integration.py --profile loam_temperate --days 120 --out out/full_integration.png
```

#### Interpretation

- Activity rises with favorable temperature, intermediate WFPS, and near-neutral pH; depth gradients arise from water and chemistry profiles.
- Higher substrate availability and quality (via `SubstrateAvailable`) increases growth through Monod response; enzyme costs reduce net growth.
- Rhizosphere priming pulses (`RhizospherePrimingPulse`) transiently amplify activity and growth near active root layers.

### SOM coupling (AGRO-79)

The microbial module receives substrate from the three-pool SOM decomposition
module (AGRO-103) via `SubstrateAvailable` events. The SOM module decomposes
labile, intermediate, and stable organic C pools and emits the microbial
growth efficiency (MGE) fraction as available substrate. This replaces the
synthetic substrate values from the old SimpleSOMRuntime placeholder.

The N cycle also subscribes to `SOMDecomposed` events to inject SOM-driven
N mineralization directly into the NH4 pool, replacing the fixed-rate
organic_n mineralization for SOM-coupled N. This creates a coherent
SOM → microbes → N cycle pipeline:

1. SOM pools decompose → emit `SubstrateAvailable` (C) + `SOMDecomposed` (N)
2. Microbial module consumes substrate → Monod growth → emit `MicrobialActivityComputed`
3. N cycle consumes `SOMDecomposed` → adds mineralized N to NH4
4. N cycle uses `MicrobialActivityComputed` to modulate residual mineralization

See also: [events](mdc:docs/events.md), [nitrogen](mdc:docs/nitrogen.md), [water](mdc:docs/water.md), and extracted notes under [Soil Microbiology](mdc:docs/soil-microbiology/index.md).


## Calibration notes (AGRO-80)

The environmental response functions (temperature, moisture as WFPS, pH) are currently modeled as bounded triangular modifiers with optima near typical literature values: temperature ≈ 30°C, WFPS ≈ 0.6, pH ≈ 6.8. Unit tests verify bounds, optima, and monotonic segments to guard against regressions. A Q10-based temperature option may be added and compared in a future iteration; for now the triangular form offers transparency and ease of calibration.

References
- Davidson, E. A., Janssens, I. A. (2006). Temperature sensitivity of soil carbon decomposition and feedbacks to climate change.
- Allison, S. D., Vitousek, P. M. (2005). Responses of soil microorganisms to moisture and temperature.
- Sinsabaugh, R. L. (2010). Phenol oxidase, peroxidase and organic matter dynamics of soil.

