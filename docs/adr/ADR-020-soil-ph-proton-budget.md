# ADR-020: Soil pH as an N-cycle proton budget buffered by pH buffer capacity

## Status

Accepted — 2026-11-18.

Edwin accepted the shared soil-pH design as proposed, decisions (a) to (d),
on 2026-11-18 (ruling relayed on #481 and #492). This ADR records that design
once for both issues:

- (a) is implemented by #492, which drafts this ADR;
- (b) by #481 PR A;
- (c) and (d) by #481 PR B.

#481's PRs amend this ADR as they land, with the status of each part.

## Context

`ChemistryState.ph` holds one pH (in water) per soil layer. It starts at
`ChemistryParams.base_ph = 6.8` on every preset and carries across
`reset_crop` and saves through `SoilSnapshot.ph`. Nitrification, NH3
volatilisation, P availability and fixation, S sorption, Fe/Zn/Mn
availability and microbial activity all read it through the
`SoilPHUpdated` cache.

Before #492, five mechanisms wrote it:

| process | rate | emitter |
|---|---|---|
| P-fixation proxy | -0.002 pH per event, one event per layer per day | `PhosphorusCycle._fix_layer` |
| NO3-leaching proxy | -0.005 pH per event | `NitrogenCycle._on_water_drained`, bottom layer only |
| acidifying fertiliser | -0.0005 pH per kg/ha | nothing in production |
| lime (#465) | rate / lime requirement, through pHBC | `apply_lime` |
| relaxation | 0.001 per day toward `DayTick.target_ph` (6.8) | every `step_day` |

Measured in the #492 refinement (150-day API seasons, urea 40/30/30):

- **Layer-0 pH ended at 6.521287 in all 16 runs.** The runs covered sand,
  loam and clay; 0 to 250 kg N/ha; rain x1, x1.5 and x2; seeds 42 and 43.
  They agreed to six decimals.
- Decomposition: -0.300 from the P-fixation proxy and +0.021 from the
  relaxation. Leaching contributed nothing.
- **The P-fixation proxy is about 1000 times too large.** Season P fixation
  in layer 0 is 0.20 / 0.95 / 2.31 kg P/ha (sand / loam / clay). Even at one
  H+ per P fixed, that is at most 0.0003 pH. Its sign is doubtful too:
  phosphate sorption by ligand exchange releases OH-.
- **The leaching proxy counts events, and in the wrong layer.** Its event
  fires only when water leaves the profile bottom, so only the bottom layer
  acidifies. Rain x2 gave 110 events and -0.275 pH there.

Over five continuous years (#481 refinement), every soil and climate reached
layer-0 pH 5.12, with the subsoil at the 4.0 floor. The equilibrium of the
clock against the relaxation is pH 4.8. Grain collapsed through the old
microbial pH triangle, which #553 replaced.

Soil acidification is the cumulative cost of N management. The model
modelled it as a clock.

## Decision

### (a) pH moves with the proton budget of the N cycle (#492)

`NitrogenCycle` accrues per-layer signed H+ (kmol/ha) from the
transformations it already computes. Stoichiometry per mol N follows Bolan,
Hedley & White 1991 (*Plant Soil* 134:53-63, doi:10.1007/bf00010717) and
Helyar & Porter 1989 (in Robson (ed.) *Soil Acidity and Plant Growth*,
pp. 61-101, doi:10.1016/b978-0-12-590655-5.50007-4):

| process | where computed | H+ per mol N |
|---|---|---|
| urea hydrolysis | `apply_urea` | -1 |
| ammonification (SOM -> NH4+) | `_on_som_decomposed`; `_mineralize_layer` when self-mineralisation is on | -1 |
| nitrification | `_nitrify_layer` | +2 |
| NO3- uptake | `_take_up_plant` | -1 |
| NH4+ uptake | `_take_up_plant` | +1 |
| denitrification | `_denitrify_layer` | -1 |
| NH3 volatilisation | `_volatilize_surface` (layer 0) | +1 |

The constants and their reactions live in `agrogame/soil/nitrogen/constants.py`.
Molar mass of N is 14.007 (IUPAC; Meija et al. 2016).

- **No leaching term.** The H+ stays in the layer where the nitrate was
  produced. Nitrate taken up deeper alkalinises that deeper layer. So "wet
  seasons acidify more" emerges from reduced uptake rather than being added.
- **Ammonium nitrate** is a neutral salt. It has no term at application; its
  NH4+ half acidifies when it nitrifies.

**Release timing.** SOM ammonification reaches the N cycle through
`SOMDecomposed`, after `NitrogenCycle.daily_step` in the same nutrients phase.
So `NitrogenRuntime` releases the day's budget at `DayTick(day_end)`, as one
`ProtonLoadOccurred(layer, h_kmol_ha)` per layer with a non-zero budget.

Urea is applied between steps, so its hydrolysis term is released at
application. Nothing is ever pending at a step boundary. A `reset_crop`,
which rebuilds the N cycle, or a save therefore loses nothing, and the
save format is unchanged (ADR-001).

**Conversion.** `SoilChemistryModule.apply_proton_load` converts the load
through the #465 buffer capacity:

```
dpH = -H+ [kmol/ha] / (pHBC [cmol/kg/pH] x soil mass [kg/ha] / 1e5)
```

The result is clamped to `[ph_floor, ph_ceiling]` = [4.0, 9.0]. Lime uses the
same scale: R kg CaCO3 is -R/50 kmol H+.

**Removed.** `apply_phosphorus_fixation` and `p_fixation_ph_delta`;
`apply_nutrient_leaching` and `no3_leach_ph_delta`; `AcidifyingFertilizerApplied`,
`apply_acidifying_fertilizer` and `acidifying_ph_delta_per_kg_ha`. The
chemistry runtime no longer subscribes to `NutrientLeached` or
`PhosphorusFixationOccurred`. Both events stay, for their own consumers.

**Omitted drivers, bounded:**

- *Base-cation removal in harvested product* (ash alkalinity): about
  0.1-0.2 kmol H+ per t of grain, or -0.004 to -0.008 pH/yr on loam at
  4-5 t/ha. That is 10-15% of the N term at 200 kg N. Product coefficients
  were not verified, so it is left out.
- *Legume N2 fixation*: soybean carries a fixed credit with no in-season
  flux, so there is nothing to attach a term to.
- *Elemental S oxidation* (S0 -> SO4 2- + 2 H+): the release schedule exists
  but is not wired to pH. A follow-up candidate.

### (b) No relaxation and no weathering term (#481 PR A)

The daily relaxation toward 6.8 is an uncited spring. With the budget alone
it caps acidification: loam at 200 kg N settles near pH 6.685, a lime dose
decays back, and lime never has a job. A relaxation toward a per-soil
"equilibrium pH" is the same spring with a different target.

A mineral-weathering alkalinity flux is citable: critical-loads weathering
classes give about +0.001 to +0.006 pH/yr for a 25-30 cm topsoil (#481
refinement, section 3; the weathering-class formula from the UNECE ICP
Modelling & Mapping Manual was quoted from memory there and must be checked
before any code cites it). But on its
own, without the carbonic-acid and bicarbonate-leaching acidity that
balances it in real soils, it makes unfertilised pH rise forever. Both
fluxes are under 0.01 pH/yr, so both are omitted.

Until PR A lands, the relaxation stays. #492 inherits it. In season 1 it
damps the budget by about 0.003 pH.

### (c) Per-preset initial pH, calcareous layers, DTPA at the soil's own pH (#481 PR B)

- Presets carry an initial pH in water. The table and its sources are in the
  #481 refinement: 6.8 for the limed temperate mineral soils, 6.5 for
  `sandy_temperate`, 5.8 for `peat_cool_wet`, 5.5 for `sandy_subsaharan`
  (source still to be cited from a table), and 8.0 for `sandy_arid`.
- Sources quoting pH(CaCl2) or pH(KCl) are converted (Minasny et al. 2011,
  *Eur. J. Soil Sci.* 62:728-732).
- Calcareous layers are a static flag, invariant under proton loads and
  lime, with no CaCO3 pool. 2% CaCO3 in a 20 cm topsoil holds about 1300
  kmol H+ of capacity, against 6-8 kmol/yr at 250 kg N: more than 150
  years. The flag adds no saved state.
- DTPA micronutrient values are read at the preset's own pH (Lindsay &
  Norvell 1978).

### (d) `clay_netherlands` is calcareous (#481 PR B)

It is a young calcareous marine polder clay, initial pH 7.8. It is the one
soil where lime is pointless, which is true of Dutch polder clays.

### Microbial activity floor at pH 4.0

#553 (PR #555) adopted Rousk, Brookes & Bååth 2009 (*Appl. Environ.
Microbiol.* 75:1589-1596): activity is 1.0 at pH 6.8 and above, falls
linearly to 2/3 at 4.5, then to **0 at 4.0**.

The #555 review noted that Rousk et al.'s own data show about 0.18 of
maximum at pH 4.0, not 0. This ADR adopts the 0 floor as implemented.

It is a modelling choice that reads the paper's "all microbial variables
were inhibited below pH 4.5" as full inhibition at the chemistry floor
(`ph_floor` = 4.0), not a fit to the data. It does not bind today:

- With the proton budget no shipped preset approaches pH 4.5 on any game
  horizon. The fastest drift measured is sand at 300 kg N: -0.11 pH in
  year 1, about -0.08 pH/yr over five years. The lowest initial pH (c)
  proposes is 5.5.
- Between pH 4.5 and 4.0 the adopted line understates activity by at most
  0.18 of maximum.

It must be revisited, toward about 0.18 at pH 4.0, before any preset with an
initial pH below 5 ships. One example is the Kenyan acid Nitisol follow-up,
at pH 4.07-4.85 (Kisinyo et al. 2013).

## Consequences

- **pH follows management.** At 0 kg N layer-0 pH holds within 0.001 over a
  season. At 200 kg N on loam it falls about 0.036 per 150-day season, at
  0.47 mol H+ per mol urea-N in layer 0. That is the efficient low end of
  Goulding 2016 (*Soil Use Manage.* 32:390-399): 0.56-1.1 mol H+ per mol N
  over a year, including product removal.
- **Buffering matters.** Clay drifts least and sand most. Rain x2 acidifies
  more, because less nitrate is taken up.
- **Five continuous years** (#492 PR evidence, every catalog scenario, seeds
  42-46): the clock took every soil to 5.12. Under the budget the
  drift scales with N rate, and lime persists (still damped by the
  relaxation until PR A). Year-5 grain is unchanged or higher in every
  catalog scenario at typical N.
- **Single-season baselines** are unchanged within 0.3% across the catalog,
  and the realism suite is unchanged.
- **Event contract.** `ProtonLoadOccurred` is new: additive in `/step`
  payloads, and the client ignores it. `AcidifyingFertilizerApplied` is gone;
  nothing ever emitted it. Per-day pH event volume falls. Each layer fixes
  P most days, and on each such event the old proxy re-published the pH of
  every layer, about n² `SoilPHUpdated` events per day. The budget emits
  one per layer per day, plus one at each urea application.
- **Ordering for #481.** PR A must assert that the P-fixation and leaching
  proxies no longer exist before it removes the relaxation. Otherwise the
  -0.30 per season clock runs free: measured 6.07 / 5.34 / 4.61 / 4.00 over
  four years.
- **#531** (continuous calendar) depends on this ADR. Continuous play under
  the clock collapsed every soil within 3-5 years.
- **#558: pH enters nitrification twice.** `NitrogenCycle._ph_factor`, an
  uncited triangle at 0 below pH 4 and 1 at 7, multiplies the nitrification
  rate. So does microbial activity, which carries the #553 pH response.
  Under the budget this double count is now a feedback on the drift itself:
  lower pH, less nitrification, less acidification. The feedback is stronger
  than either factor alone. It belongs under this ADR and is fixed in #558,
  not here.

## Alternatives Considered

- **Rescale the P-fixation proxy.** It has no basis and its sign is doubtful.
- **Keep a per-kg leaching term.** It double-counts under the budget: the
  acidity of leached nitrate is already in the layer that produced it.
- **Release at the end of `NitrogenCycle.daily_step`.** SOM ammonification
  arrives after it in the same phase, so a day of protons would carry to the
  next day. Rejected (#492 AC12).
- **Hold urea hydrolysis until `day_end`.** `reset_crop` between the
  application and the step would lose it, and so would a save. Carrying it
  would need new saved state. Rejected.
- **A CaCO3 pool for calcareous soils.** Exact to the flag on any game
  horizon, at the cost of saved state.
- **A relaxation toward a per-soil equilibrium pH.** The same spring:
  it undoes lime and caps acidification.

## References

- #492 (proxies, budget, measurements), #481 (shared refinement, presets,
  calcareous, DTPA), #553 / PR #555 (microbial pH response), #558 (double pH
  in nitrification), #465 / #491 (buffer capacity and lime), #531.
- Bolan, Hedley & White 1991, *Plant Soil* 134:53-63.
- Helyar & Porter 1989, in Robson (ed.) *Soil Acidity and Plant Growth*,
  pp. 61-101.
- Goulding 2016, *Soil Use Manage.* 32:390-399.
- Rousk, Brookes & Bååth 2009, *Appl. Environ. Microbiol.* 75:1589-1596.
- Curtin & Rostad 1997, *Can. J. Soil Sci.* 77:621-626; Aitken & Moody 1994,
  *Aust. J. Soil Res.* 32:975-984 (buffer capacity).
- Lindsay & Norvell 1978, *SSSAJ* 42:421-428 (DTPA soil test).
- Minasny et al. 2011, *Eur. J. Soil Sci.* 62:728-732 (pH medium conversion).
- Kisinyo et al. 2013, *Sustain. Agric. Res.* 2(2):116.
- Meija et al. 2016, *Pure Appl. Chem.* 88:265-291 (atomic weights).
