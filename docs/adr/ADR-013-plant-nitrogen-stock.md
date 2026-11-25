# ADR-013: Whole-shoot plant-nitrogen accounting (critical-N dilution)

## Status

Accepted (2026-07-03) — [#360](https://github.com/gedejong/agrogame/issues/360)
(follow-up to #351 / #357).

### Amendment 2026-09-07 — uptake is demand-driven; mass flow is a diagnostic

Decision point 3 described soil N uptake as "mass-flow (soil-supply) limited".
The uptake in `NitrogenCycle._take_up_plant` is demand-driven and capped by the
mineral N available in each rooted layer. The transpiration mass-flow term is
computed for diagnosis only and published as
`MassFlowNSupplyComputed(total_kg_ha, by_layer)`; it neither debits the nitrate
pool nor credits the plant stock. Debiting it removed nitrate that no plant
stock ever received (of the order of 100 kg N/ha per season under a full maize
canopy), and crediting it would double-count the demand-driven uptake.

### Amendment 2026-11-18 — no N uptake before emergence; no demand floor ([#578](https://github.com/gedejong/agrogame/issues/578))

Decision point 4 makes the N demand the deficit to critical, and the
Persistence section has a new crop start with ~0 shoot N. The orchestrator
nonetheless returned `max(0.1, deficit)`, an uncited floor that took
0.1 kg N/ha/day from the soil from the sowing day. The stock banked 2-3 kg N/ha
behind the 1.0 NNI sentinel before emergence, and on the first seedling day it
divided by a near-zero shoot DM: NNI 9.7 under the legacy Netherlands weather
and up to 39 under De Bilt station normals.

The demand for a planted crop is now exactly the deficit to critical, with no
floor. It is 0 while shoot DM is at or below 1 kg/ha (before emergence) and 0
whenever the stock is at or above critical, so no soil N is taken up before
emergence. This follows CERES-Maize, where DSSAT-CSM `MZ_CERES.for` runs growth
and N uptake only for ISTAGE 1-6, emergence to maturity (Jones et al. 2003,
*Eur. J. Agron.* 18:235-265), and APSIM Next Generation PMF, whose
`OrganArbitrator` estimates and sets N uptake only when `plant.IsEmerged`
(Brown et al. 2014, *Environ. Model. Softw.* 62:385-398). Neither model has a
demand floor.

### Amendment 2026-11-24 — no N uptake after maturity ([#539](https://github.com/gedejong/agrogame/issues/539))

The post-maturity counterpart of the #578 amendment. Shoot DM is frozen at
MATURITY (#433), so the critical-N target is fixed, and a crop standing below
critical kept filling its stock to that target: Kenya maize gained about
85 kg N/ha over 300 standing days on top of the 94 it took up in the season,
and scavenged every kilogram the soil mineralised meanwhile. Under #531 a
mature crop stands until the player harvests it, so this reached play.

The N demand is now 0 while the phenology stage is MATURITY, so the stock
holds at its maturity value. CERES-Maize runs growth and uptake only for
ISTAGE 1-6, setting `UNO3 = UNH4 = PUptake = 0` otherwise, and ISTAGE 6 itself
returns with no N or K uptake (DSSAT-CSM `MZ_CERES.for:665-740`,
`MZ_GROSUB.for:1621-1623`; Jones et al. 2003, *Eur. J. Agron.* 18:235-265).
The WOFOST crop parameter files define `DVS_NPK_STOP`, the development stage
above which no crop N/P/K uptake occurs (de Wit et al. 2019, *Agric. Syst.*
168:154-167); PCSE declares the parameter but does not apply it, so it is cited
as the WOFOST definition, not as PCSE behaviour.

P, S, Fe, Zn and Mn uptake stop on the same rule: P and S demand are 0 at
MATURITY, ahead of their 0.01 and 0.005 kg/ha/day floors, and the micronutrient
pools equilibrate as on a fallow patch (#542). Before this they kept drawing on
the last grain-fill day's growth increment, which no longer updates once
growth stops. Water uptake is not gated: transpiration follows green LAI
through the late season, as the FAO-56 late-season crop coefficient declines
to Kc_end without a step to zero (Allen et al. 1998, Table 12). The root front
stops at MATURITY too, and root turnover continues (APSIM Next Generation
`Root.cs`). Every gate reads the saved phenology stage, so no runtime memory is
added (#585). The `/forecast` mineral-N projection drops its crop-uptake sink
for a mature anchor.

> **Superseded by the 2026-11-25 amendment (#623):** the sentence "Water uptake
> is not gated: transpiration follows green LAI through the late season, as
> the FAO-56 late-season crop coefficient declines to Kc_end without a step to
> zero" no longer holds after maturity. A determinate crop now has no green
> leaf from its first MATURITY step.

### Amendment 2026-11-25 — no green leaf after maturity ([#623](https://github.com/gedejong/agrogame/issues/623))

This replaces the 2026-11-24 water sentence. The FAO-56 late-season decline
to Kc_end describes the crop before harvest; it does not license the green
canopy that kept transpiring after physiological maturity, where green LAI
decayed only at the peak grain-fill senescence rate (e-folding 50 days for
maize, 62 for spring wheat). A standing NL spring wheat crop transpired 91 mm
in the 60 days after maturity, against 127 mm in its season, and standing
Sahel maize and sorghum 95 and 102 mm (medians, seeds 42-51).

A determinate crop (maize, wheat, sorghum, rice, soybean) now senesces all
green leaf at its first MATURITY canopy step, so LAI is 0.0 from that day and
transpiration, rain interception and the client follow it with no separate
gate. WOFOST ends the crop at DVSEND by default and nothing transpires after
(`crop_finish`; PCSE `phenology.py:473-476`, `engine.py:330-333`,
`classic_waterbalance.py:421-422`); DSSAT-CSM harvests at maturity unless the
experiment file says otherwise (`IHARI = 'M'`; `AUTHAR.for:152-154`,
`IPSIM.for:155`). Where the crop stands, CERES-Wheat senesces the last green
leaf to zero at LSPHE 6.3, 60 °C·d after maturity (`CER_Growth.for:818-822`,
`WHCER048.ECO`/`.SPE`), and FAO-56 gives field-dried grain maize a Kcb_end of
0.15, which is Kc_min for dry bare soil (Allen et al. 1998, Tables 12 and 17).
Grape is exempt through the preset flag `green_leaf_dies_at_maturity`: its
MATURITY is fruit ripeness on a deciduous vine that keeps its leaves until
leaf drop (FAO-56 Table 12, footnote 18).

The gate reads the saved phenology stage, so a save taken after maturity
before this change loses its green leaf at the first step after loading, and
no runtime memory is added (#585). The canopy phase runs after `et`
(ADR-010), so the season to maturity is unchanged. One consequence was
accepted with the ruling: the standing crop no longer dries the profile, so a
resown Sahel crop starts on stored subsoil water (resown maize grain about
+60% median, sorghum about +12%); #662 checks that carry-over against the
model's dry-season soil evaporation.

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
- **Amendment 2026-11-24 (#603): the flat-below threshold is per crop.**
  Justes et al. (1994), *Ann. Bot.* 74:397-407, state the wheat law holds
  between 1.55 and 12 t/ha and give a constant N_ct = 4.4 % below 1.55 t/ha;
  `5.35 · 1.55^-0.442 = 4.408 %`, so the curve is continuous there and the
  existing `max(W, reference)` form reproduces the cited constant with
  `reference_biomass_t_ha = 1.55` (preset key `n_crit_reference_biomass_t_ha`).
  Wheat uses 1.55; every other crop keeps 1.0 (the Greenwood et al. 1990
  domain, W > 1 t/ha). Previously wheat was held at 5.35 % below 1 t/ha,
  21 % above the cited constant.
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
