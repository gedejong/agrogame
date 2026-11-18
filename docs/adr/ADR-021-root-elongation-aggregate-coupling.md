# ADR-021: Root elongation does not read aggregate structure

## Status

Accepted, 2026-11-18. Edwin de Jong chose Option B of
[#526](https://github.com/gedejong/agrogame/issues/526) on 2026-11-18 ("all as
recommended", relayed by the manager session and recorded on the issue),
including this ADR and the season-2 baseline move measured at the refinement
base (−16.6 % on NL loam, −17.2 % on NL clay; table below). Implemented by
#526.

The larger move on main as of `477a578` (−18.6 % on NL loam, −16.7 % on NL
clay), which comes from engine changes merged after the ruling (#553, #605),
was sent to Edwin for re-confirmation on 2026-11-18. That re-confirmation is
pending and is to be recorded here when given.

## Context

`RootsRuntime` passed `root_penetration_factor(agg_state.mwd(0))`
(`agrogame/soil/aggregation/dynamic_state.py`) to `RootModule.daily_step` as a
whole-profile multiplier on the daily root-elongation rate. The factor rises
linearly from 0.3 at a topsoil mean weight diameter (MWD) of 0 to 1.0 at
2 mm. The API forecast mirrored it (#383).

Tillage destroys topsoil macroaggregates, so a moldboard pass slowed rooting.
The #526 refinement measured it on loam × `netherlands_temperate` (maize,
150 kg N/ha ammonium nitrate on day 0 of each season, two 150-day seasons from
2024-04-15 and 2025-04-15 with weather seeds 42 and 43, `harvest()` then
`reset_crop` between them):

- A pass at the start of each season took topsoil MWD from 0.551 to 0.218 mm
  and the elongation factor from 0.493 to 0.376. Root depth at day 60 fell by
  21 % in season 1 and 31 % in season 2.
- Grain moved by +15.6 % in season 1 and −30.0 % in season 2 (−17.6 % in
  season 2 after a single pass in season 1). On clay, in Kenya and in the Sahel,
  season 1 was −10 to −15 %, and Sahel season 2 was −45 %.
- Lockstep knockouts attributed 99–100 % of both seasons' grain change to this
  channel. SOM protection, mineral N, the Ksat factor, biopores and saturation
  together contributed at most 0.6 g/m².

The literature has the opposite sign and a far smaller magnitude. Tillage
lowers plough-layer bulk density: Lampurlanés & Cantero-Martínez (2003)
report 1.34 Mg m⁻³ under no-till against 1.22–1.27 under subsoil and minimum
tillage. Zero tillage raises surface bulk density and penetration resistance
(Grant & Lafond 1993). Yet root growth differs little between tillage systems,
and root length density is sometimes greater under no-till. The root fronts of
CERES-Maize and APSIM have no aggregate-structure or tillage term. Across the
Pittelkow et al. (2015b) meta-analysis, maize under no-till yields 7.6 % below
conventional tillage, so a pass should cost nothing or gain a few per cent,
never −30 %.

The season-1 *gain* on NL loam has a second cause, non-compensatory root water
uptake (#535). It sets the sign in season 1 but not the size of the effect.

## Decision

**Root elongation does not read aggregate structure.** `RootsRuntime` passes a
constant, `CALIBRATED_ROOT_ELONGATION_FACTOR`, defined once in
`agrogame/soil/aggregation/dynamic_state.py` as
`root_penetration_factor(SoilAggregationState.from_layers(1).mwd(0))`: the
factor at the default initial structure (40 % micro, 35 % meso, 25 % macro;
MWD 0.55125 mm), which is 0.4929375.

- **It preserves the calibration.** Every crop's root front ran under exactly
  this value on day 0 when the realism suite was calibrated, so season 1 and
  every realism bound stay in place.
- **It is not a soil-strength parameter.** It stands for no measured soil
  property and must not be tuned as one. Any future dependence of rooting on
  soil structure arrives through the model described under "Path forward",
  not by making this constant vary.
- **The engine and the forecast share it.** `agrogame/api/routes.py` threads
  the same constant into `project_soil_forecast`, so the #383 mirror stays
  exact. `RootsRuntime` no longer holds `agg_state`.

Unchanged: tillage still destroys macroaggregates (`AggregationModule`), and
they still feed SOM physical protection (`SOMRuntime`) and the Ksat factor
(`WaterRuntime`). `root_penetration_factor` is kept as the function that
defines the constant. No `*Params` default, preset or save field changes,
because the coupling held no state of its own.

## Consequences

### The untilled multi-season baseline moves

Untilled maize grain (g/m²) at the #526 setup, before and after this change.
Kenya seasons start on 03-01 and Sahel seasons on 06-01. Season 1 moves by at
most 2.6 %. Season 2 falls, because the structure that builds up through
season 1 (MWD 0.55 → 1.01 mm over two seasons) no longer speeds the untilled
crop's roots. Lampurlanés & Cantero-Martínez (2003) do not support that
speed-up either.

| scenario | S1, refinement base `5599030` | S2, refinement base `5599030` | S1, main as of `477a578` | S2, main as of `477a578` |
|---|---|---|---|---|
| NL × loam | 470.1 → 481.0 (+2.3 %) | 356.7 → 297.5 (−16.6 %) | 470.1 → 481.0 (+2.3 %) | 401.3 → 326.7 (−18.6 %) |
| NL × clay | 586.4 → 574.6 (−2.0 %) | 351.9 → 291.2 (−17.2 %) | 586.4 → 574.6 (−2.0 %) | 402.0 → 334.9 (−16.7 %) |
| Kenya × loam | 512.3 → 498.8 (−2.6 %) | 397.0 → 363.9 (−8.3 %) | 516.7 → 503.3 (−2.6 %) | 416.5 → 382.9 (−8.0 %) |
| Sahel × loam | 176.9 → 174.6 (−1.3 %) | 92.9 → 78.3 (−15.7 %) | 176.9 → 174.6 (−1.3 %) | 96.8 → 84.8 (−12.4 %) |

The refinement base `5599030` is where the #526 prototype was measured and the
ruling was given. The implementation reproduces the prototype there to
0.0 g/m², and that column is the stable reference for this decision.

The main column is a snapshot as of `477a578`. Later engine merges will move
it again, and only the refinement-base column is fixed. Two engine merges after
the ruling moved season-2 grain without changing root depth, so the column
departs from the prototype. Bisecting by first-parent merge found them, and a
third, #578, was checked and moves nothing:

| change (merge) | season-2 NL-loam grain, coupled | season-2 NL-loam grain, this decision |
|---|---|---|
| #553 (`6ad5a0e`, microbial pH response) | +35.6 g/m² | +13.1 g/m² |
| #605 (`dcc8926`, soil pH proton budget) | +9.1 g/m² | +16.0 g/m² |
| #578 (`477a578`, no N uptake before emergence) | 0.0 g/m² | 0.0 g/m² (≤ 0.01 in every scenario) |

On NL loam, #553 widened the relative season-2 move from −16.6 % to −20.8 %,
and #605 narrowed it to −18.6 %. On NL clay the move is −17.2 % at the
refinement base and −16.7 % as of `477a578`. Day-60 root depth is identical
before and after each merge.

No realism bound covers season 2, and `tests/integration/test_realism.py` is
unchanged and passes.

### Tillage no longer moves rooting

A pass now leaves root depth identical to the untilled crop's on every day
of both seasons, in every scenario above. On the refinement base it moves grain
by at most 0.2 % on NL loam and clay, and by −1.8 % in Sahel season 2. As of
`477a578` the figures are at most 2.2 % on NL (loam, season 2, a pass in each
season) and −5.0 % in Sahel season 2. Lockstep knockouts as of `477a578`
attribute the residual to the Ksat factor, a channel this decision keeps.
Handing the tilled run's `WaterRuntime` the untilled aggregate state takes NL
loam season 2 from −2.22 % to −0.01 %, and the Sahel from −5.00 % to 0.00 %.
SOM protection accounts for 0.01 percentage points, and the pore-network
partition for none. #553 and #605 amplified this channel after the
refinement. `tests/integration/test_tillage_response.py`
asserts identical depth and |Δgrain| ≤ 10 %; the bound is on magnitude, not
sign, because the engine models none of the mechanisms behind tillage's yield
advantage.

### Harder

- Rooting no longer responds to soil structure at all, so a compacted or
  well-structured soil roots at the same speed. That is the honest state of the
  engine until the model below exists: the coupling it replaces had the wrong
  sign.
- Studies quoting multi-season untilled yields from before #526 must be re-run.
  #535's refinement emulated this decision by fixing the factor at 0.4929375,
  so its tables at the refinement base remain valid.

## Path forward

A future soil-strength model needs, in order:

1. **Compensatory root water uptake first** (#535). With non-compensatory
   uptake, deeper or faster rooting can cost grain (#526, #524 W3), so any
   rooting physics would be calibrated against an artefact.
2. **Bulk-density loosening by tillage and reconsolidation by rainfall**, as in
   EPIC (Williams, Jones & Dyke 1984).
3. **Root stress from bulk density** (soil strength), as in Jones, Bland,
   Ritchie & Williams (1991), applied per layer with a per-layer rooting front
   rather than a whole-profile multiplier read from the topsoil.

That is #526's Option C, sized XL. It needs its own ADR superseding this one,
and it will move realism bounds.

## Alternatives Considered

### Option A: keep the coupling, with a tillage floor

Never let a pass lower the factor below its pre-pass value. Untilled runs would
stay bit-identical, but the untilled structure keeps building while the tilled
one restarts, so season 2 still fell by 16–17 % on both soils. It fails the
literature, and it would need a new persisted field in `SoilSnapshot`.

### Option C: tillage physics now

The path forward above. Rejected for now: it is XL and unsafe before
compensatory uptake exists.

## References

- Issue #526 (this decision; the refinement comment holds the measurements,
  knockouts and the Option A/B/C analysis). #535: compensatory root water
  uptake. #536: weak SOM response to tillage. #383: the forecast mirror.
  #524: the earlier retirement of root-penetration claims the engine cannot
  ground.
- Lampurlanés, J. & Cantero-Martínez, C. 2003. Soil bulk density and
  penetration resistance under different tillage and crop management systems
  and their relationship with barley root growth. *Agron. J.* 95: 526–536.
  doi:10.2134/agronj2003.5260
- Grant, C.A. & Lafond, G.P. 1993. The effects of tillage systems and crop
  sequences on soil bulk density and penetration resistance on a clay soil in
  southern Saskatchewan. *Can. J. Soil Sci.* 73: 223–232. doi:10.4141/cjss93-024
- Pittelkow, C.M. et al. 2015b. When does no-till yield more? A global
  meta-analysis. *Field Crops Res.* 183: 156–168. doi:10.1016/j.fcr.2015.07.020
- Williams, J.R., Jones, C.A. & Dyke, P.T. 1984. A modeling approach to
  determining the relationship between erosion and soil productivity.
  *Trans. ASAE* 27: 129–144. doi:10.13031/2013.32748
- Jones, C.A., Bland, W.L., Ritchie, J.T. & Williams, J.R. 1991. Simulation of
  root growth. In: Hanks, J. & Ritchie, J.T. (eds), *Modeling Plant and Soil
  Systems*, Agron. Monogr. 31: 91–123. doi:10.2134/agronmonogr31.c6
- Jones, C.A. & Kiniry, J.R. (eds) 1986. *CERES-Maize: A Simulation Model of
  Maize Growth and Development.* Texas A&M University Press.
- Keating, B.A. et al. 2003. An overview of APSIM, a model designed for farming
  systems simulation. *Eur. J. Agron.* 18: 267–288.
