# ADR-013: Whole-shoot plant-nitrogen accounting (critical-N dilution)

## Status

Accepted (2026-07-03) — [#360](https://github.com/gedejong/agrogame/issues/360)
(follow-up to #351 / #357).

## Context

Before this change the crop's N-stress signal was **flow-based**: the
nitrogen runtime compared the day's soil N uptake against the day's demand
(`clamp(uptake / demand, 0..1)`) and fed that ratio into the canopy's Liebig
`min()` on RUE. Because same-day demand is small and usually met, the ratio
sat near 1 (satisfied) or collapsed to near 0 (starved), giving a **bimodal**
on/off response with little middle ground. A realistic, high-magnitude,
*graded* response to fertiliser rate needs a **stock** of plant N compared
against a **critical-N dilution curve**, as in DSSAT (CERES) and APSIM.

## Decision

1. **Whole-shoot, not per-organ.** Track a single whole-shoot N stock
   (kg/ha) rather than per-organ (leaf/stem/grain) pools. This is the
   Greenwood / Justes / Plénet–Lemaire critical-N framework and keeps the
   scope at L. Per-organ accounting is a possible future refinement.

2. **New `agrogame/plant/nitrogen/` package.** The stock, the critical-N
   curve, the NNI, and the NNI→stress mapping live in a dedicated plant-side
   package (`params.py` / `state.py` / `module.py` / `runtime.py`) rather
   than being bolted onto `NitrogenCycle`/`NitrogenRuntime`. The nitrogen
   cycle is already the #3 "god node" in the dependency graph; adding
   plant-physiology logic there would deepen the coupling. The change is
   *additive*: a new layer that consumes the existing soil N uptake.

3. **Uptake unchanged; stress derived from the stock.** Soil N uptake stays
   mass-flow (soil-supply) limited in `NitrogenCycle._take_up_plant` — we do
   **not** change how uptake is limited. The nitrogen runtime stops emitting
   the flow-based `NutrientStressComputed` and instead emits
   `PlantNUptakeComputed(uptake, demand)`. `PlantNitrogenRuntime` consumes it,
   accumulates the stock, computes the N nutrition index, and emits the single
   graded `NutrientStressComputed(N)` the canopy reads.

4. **Stock-based N demand.** The N *demand* handed to the nitrogen cycle is
   now the deficit between the stock and the critical-N target for the
   current shoot DM (DSSAT/APSIM crop N demand), replacing the legacy
   same-day `biomass_increment × tissue_conc × 0.5` formula for N. Without
   this, the 0.5 same-day-remobilisation cap held cumulative uptake at ~half
   the crop's need, so the stock could never approach critical N and NNI was
   pinned low regardless of fertiliser. P demand keeps its own formula.

5. **Liebig `min()` retained at the canopy.** Gradedness comes from NNI being
   *continuous*, not from switching the canopy to a multiplicative combiner.

6. **Cross-domain event placement.** `PlantNUptakeComputed` lives in
   `agrogame.plant.events` alongside `NutrientStressComputed`, so the
   soil → plant import (`soil.nitrogen.runtime → plant.events`) reuses the
   already-whitelisted event-subscription edge (ADR-008); the plant layer
   never imports `soil.nitrogen`.

## Model

For shoot dry matter `W` (t/ha) and stock `N_stock` (kg/ha):

- Critical N: `N_crit% = a · W^-b`, held flat below a reference biomass
  (~1 t/ha) to avoid the `W → 0` divergence. Coefficients:
  - **maize** `3.40 · W^-0.37` — Plénet & Lemaire (2000), *Plant & Soil*
    216:65–82 (orig. 1999).
  - **wheat** `5.35 · W^-0.442` — Justes et al. (1994), *Ann. Bot.*
    74:397–407.
  - **fallback** (crops without a fitted curve) `5.70 · W^-0.50` — the
    generic C3 dilution of Greenwood et al. (1990), *Ann. Bot.* 66:425–436.
- Actual N: `N_actual% = 100 · N_stock / (W·1000)`.
- NNI: `N_actual% / N_crit%` (Lemaire & Gastal 1997).
- Stress: a documented linear rescale of NNI between `nni_stress_min` and
  `nni_stress_ref`, clamped to `[stress_floor, 1]`. Luxury uptake (NNI > 1)
  is capped at 1.0 (no growth bonus). The defaults
  (`min=0, ref=1, floor=0.05`) give `clamp(NNI, 0.05..1)` with the luxury cap;
  the anchors exist as a CERES-Maize-NFAC-style calibration lever
  (Jones et al. 2003).

## Persistence

The whole-shoot N stock is a **within-season** plant property and is
intentionally **not** persisted in `SoilSnapshot` (which captures soil pools
only). A new crop starts with ~0 shoot N; `reset_crop` rebuilds
`plant_n_state` fresh. This is covered by a two-cycle test.

## Consequences

- Fertiliser dose-response over 0–240 kg N/ha is monotone, smooth and
  saturating (Mitscherlich-type), with the agronomic knee (~90% of max)
  around 120–160 kg N/ha on the N-depleted Kenya-highlands maize scenario.
- The N-demand trajectory front-loads (building the stock during
  establishment/grand growth, then tapering) rather than tracking the daily
  biomass increment; the demand-trajectory realism test was updated to match.
- All existing realism bands (NL/Kenya/Sahel, `fertilized > 3× unfertilized`)
  stay green.
