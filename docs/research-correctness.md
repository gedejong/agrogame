### Research: Scientific Correctness Status and Next Steps

This note captures the current state of scientific correctness across AgroGame, evidence from automated checks and diagnostics, and a concrete plan to harden validation.

#### Evidence snapshot (current build)

- Full-integration expectations report: 6/8 checks passed; two flagged:
  - Low water stress implies low supply: failing under current settings
  - Actual ET exceedance fraction < 0.10: exceedances present on stress days
- ET/Water diagnostics:
  - Days with E+T >> ET0 occur when evaporation peaks during very low LAI; indicates ET0 proxy or partitioning assumptions may be inconsistent in those regimes.
- Nutrients:
  - P-stress correlates positively with top-layer available P (proxy) as expected.
  - N coherence check skipped due to missing columns earlier; CSV now includes `n_total_kgha` enabling future checks.
- Canopy/Phenology:
  - LAI grows then plateaus/declines (OK)
  - Biomass monotonic non-decreasing (OK)
- Microbes:
  - Event-backed diagnostics render consistently across patterns; no numerical instabilities observed in surface/depth splits.

Key artifact for this run: `out/expectations_full_integration.md` (generated from expectations suite) and timeseries CSV `out/full_integration_timeseries.csv`.

#### Likely causes of flagged checks

- Water supply vs stress mismatch:
  - Current check uses `transp_mm/pot_transp_mm` with LAI and minimum potential demand gates. Exceedances suggest either:
    - Potential transpiration too low under certain meteorology/LAI → revisiting Priestley–Taylor inputs or VPD handling
    - Evaporation component overestimated under bare/near-bare soil → re-check soil evaporation cap and stage-1/stage-2 transitions
- E+T > ET0 exceedance fraction:
  - ET0 reference (PT) may under-estimate under windy/dry days if not including aerodynamic term; consider Penman–Monteith option for reference consistency.

#### Proposed implementation plan (validation-focused)

1) Tighten ET reference and partitioning
- Add PM reference option across plots and expectations; default to PM when wind/RH present, fallback to PT otherwise.
- Cap evaporation using standard stage-1/2 soil evaporation model (e.g., Ritchie) with soil moisture and cumulative depletion gates.
- Recompute expectations with PM and revised E model; update thresholds accordingly.

2) Strengthen water-stress coherence checks
- Use transpiration supply-demand ratio gated by LAI and `pot_transp_mm >= 1.0` as today, but:
  - Split diagnostics by growth phases to isolate early-season edge cases.
  - Report quantiles and exceedance bands; target mean ≤ 0.65 with ≤ 10% exceedance after fixes.

3) Add nutrient coherence assertions
- Use newly exported `n_total_kgha` and event-based `NutrientStressComputed` to check monotone relationship between available N and N-stress at fixed LAI bands.
- Extend P check with layer-weighted availability where roots are present; use Spearman ρ ≥ 0.2 and quartile monotonicity.

4) Phenology and canopy alignment
- Add flowering/maturity window checks to expectations using phenology events; assert within configured windows per crop preset.
- Validate Beer–Lambert interception consistency: `I = 1 - exp(-k*LAI)` versus canopy module outputs; add tolerance check.

5) Add baseline benchmark harness
- Curate 2–3 public scenarios (maize, wheat) with observed daily biomass/LAI (or yield-only if daily absent).
- Compute R², NSE, MAE; enforce minimums (R² > 0.9, NSE > 0.8) on at least one canonical scenario.

6) Expand artifacts and docs
- Persist per-run `expectations_*.md` and CSVs under `out/` with pattern and seed metadata.
- Document methodology and thresholds in `docs/validation.md` and link this page.

#### Task breakdown (ready to implement)

- ET/Reference
  - Add Penman–Monteith reference to ET module and wiring in plots; flag-select PT/PM.
  - Implement soil evaporation stage model; integrate into water module and ET partitioning used in diagnostics.
- Expectations suite
  - Update water-stress coherence and ET exceedance checks with phase splits and PM option.
  - Add N coherence and enhanced P availability checks (layer-weighted by root density).
  - Add phenology window assertions based on emitted events.
  - Add interception identity check against Beer–Lambert.
- Benchmarks
  - Add fixture(s) for observed series/yield; create benchmark tests invoking the suite.
- Documentation
  - Update `docs/validation.md` with methodology; link this page under Validation.

#### Acceptance criteria

- All expectations pass on default scenario (≥ 8/8).
- No ET exceedance fraction > 0.10 with PM reference and revised evaporation.
- Water-stress mean ratio ≤ 0.65 with ≤ 10% exceedance in active growth.
- Benchmark test suite meets R² > 0.9 and NSE > 0.8 on canonical crop; yield within ±10% window.
- Documentation updated and plots regenerated.
