### Microbial biomass and enzyme activity (AGRO-78)

This module simulates microbial biomass dynamics with environmental controls and enzyme production, and exposes depth-resolved diagnostics for visualization and coupling with nutrient cycles.

- Events: `MicrobialGrowthOccurred`, `MicrobialMortalityOccurred`, `EnzymeProduced`, `EnzymeGroupTotalsComputed`, `MicrobialActivityComputed`, `MicrobialFBUpdated`, `SubstrateReleased`, `RhizospherePrimingOccurred`.
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
- Higher substrate availability and quality (via `SubstrateReleased`) increases growth through Monod response; enzyme costs reduce net growth.
- Rhizosphere priming pulses (`RhizospherePrimingOccurred`) transiently amplify activity and growth near active root layers.

### SOM coupling (AGRO-79)

The microbial module receives substrate from the three-pool SOM decomposition
module (AGRO-103) via `SubstrateReleased` events. The SOM module decomposes
labile, intermediate, and stable organic C pools and emits the microbial
growth efficiency (MGE) fraction as available substrate. This replaces the
synthetic substrate values from the old SimpleSOMRuntime placeholder.

The N cycle also subscribes to `SOMDecomposed` events to inject SOM-driven
N mineralization directly into the NH4 pool, replacing the fixed-rate
`organic_n` mineralization for SOM-coupled N. This creates a coherent
SOM → microbes → N cycle pipeline:

1. SOM pools decompose → emit `SubstrateReleased` (C) + `SOMDecomposed` (N)
2. Microbial module consumes substrate → Monod growth → emit `MicrobialActivityComputed`
3. N cycle consumes `SOMDecomposed` → adds mineralized N to NH4
4. N cycle uses `MicrobialActivityComputed` to modulate its own residual
   `organic_n` mineralization — **in standalone mode only** (see below)

**SOM-authoritative in the full sim (#351).** The full
`FullSimulationOrchestrator` builds the nitrogen cycle with
`NitrogenRateParams.enable_self_mineralization = False`, so the 3-pool RothC
SOM module (Coleman & Jenkinson 1996) is the *single* authoritative
mineralization source and its N flux enters via `SOMDecomposed` (step 3). In
this path there is no residual `organic_n` mineralization left to modulate, so
step 4 is inert and the `organic_n` pool is kept inert for mass balance; the
"replaces the fixed-rate `organic_n` mineralization" statement above is
therefore literally true in the full sim. Running both paths at once
double-counted the same physical soil organic N and roughly quintupled net
mineralization (~14 vs ~1–3 kg N/ha/day; Stanford & Smith 1972).

In **standalone mode** (`enable_self_mineralization = True`, the default —
preserving unit-test and standalone-cycle behaviour) the cycle still runs its
own `organic_n` mineralization and step 4's `MicrobialActivityComputed`
modulation applies as described.

See also: [events](mdc:docs/events.md), [nitrogen](mdc:docs/nitrogen.md), [water](mdc:docs/water.md), and extracted notes under [Soil Microbiology](mdc:docs/soil-microbiology/index.md).


### Initial pool sizing

`ThreePoolSOM.initialize_from_profile` derives each layer's total organic C
from the profile (OM % x bulk density x depth x 0.58) and splits it between
the pools at the **kinetic steady state of the module's own rate constants**
(`steady_state_fractions`). Under a constant fresh-C input *F* the pools
settle at

    C_lab = F / k_lab_eff
    C_int = h_li * F / k_int_eff
    C_stb = h_li * h_is * F / k_stb_eff

where `k_*_eff` are the protection-adjusted rate constants for the layer's
clay content and `h_*` the humification fractions, so the shares depend on
neither *F* nor the environmental factor. On a 22 % clay loam that is about
2 % labile, 32 % intermediate and 66 % stable; clays hold less labile C
because protection slows the intermediate and stable pools most. This is the
equilibrium initialisation RothC and Century use (Coleman & Jenkinson 1996;
Parton et al. 1987).

Fresh-C input declines roughly exponentially with depth (Jackson et al. 1996;
Jobbagy & Jackson 2000), so the labile and intermediate shares of deeper
layers are scaled by `exp(-(z_mid - z_mid_topsoil) /
fresh_input_efolding_depth_cm)` (default 30 cm) and the stable pool takes
the remainder. Pool N follows the fixed C:N ratios 12 / 15 / 20.

The input-fed equilibrium is only a prior: without continuing fresh inputs,
its fast pool still produces a first-season flush. New fields therefore
condition the shares through a reference 60-day bare-soil interval at 17 °C
and 60 % WFPS, with no fresh inputs or priming. The resulting C shares are
normalised to the measured total SOC and assigned the pool C:N ratios.
This is an explicit initial-state assumption, not a simulated C input or a
claim about a field's actual history. Set `initial_fallow_days=0` to retain
the input-fed prior. Decomposition rates are unchanged. The pool
object is a preserved state container: a crop reset hands it to the rebuilt
runtime, so seasons carry their decomposed pools forward. See
[ADR-015](adr/ADR-015-som-steady-state-initialisation.md).

## Calibration notes (AGRO-80)

The environmental response functions (temperature, moisture as WFPS, pH) are currently modeled as bounded triangular modifiers with optima near typical literature values: temperature ≈ 30°C, WFPS ≈ 0.6, pH ≈ 6.8. Unit tests verify bounds, optima, and monotonic segments to guard against regressions. A Q10-based temperature option may be added and compared in a future iteration; for now the triangular form offers transparency and ease of calibration.

References
- Davidson, E. A., Janssens, I. A. (2006). Temperature sensitivity of soil carbon decomposition and feedbacks to climate change.
- Allison, S. D., Vitousek, P. M. (2005). Responses of soil microorganisms to moisture and temperature.
- Sinsabaugh, R. L. (2010). Phenol oxidase, peroxidase and organic matter dynamics of soil.
