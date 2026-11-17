# ADR-016: Preferential flow is structural, not hydrological (dual-porosity model retired)

## Status

Accepted — decided 2026-10-02 (Option B of #466), implemented by #466.
Amends [ADR-010](ADR-010-pore-chain-phase-ordering.md). Expected to be
superseded by the ADR that #485 (Preferential flow v2) will require.

## Context

#213 delivered `DualPorosityWaterModel` and `DualPorosityParams`
(`agrogame/soil/water/models/dual_porosity.py`), a first-order exchange helper
(`dual_porosity_exchange.py`) and a `PreferentialFlowOccurred` event, as part of
the pore-network umbrella #74. The model was MACRO/RZWQM-style. It split
rainfall between the matrix and a macropore domain by rainfall intensity
against topsoil Ksat, routed the bypass share through macropore storage, and
returned it to the matrix through a first-order exchange term (Jarvis 2007;
Gerke & van Genuchten 1993; Ahuja et al. 2000). It carried unit and realism
tests.

The model never ran in the simulation. `FullSimulationOrchestrator` builds
`CascadingBucketWaterModel` unconditionally, and nothing in `agrogame/`
constructed the dual-porosity model. ADR-010 recorded the wiring as deferred,
but its Consequences section still claimed that heavy-rain bypass surfaced in
simulation outputs. That was false. #466 asked to wire the model in or retire
it.

The pore chain reaches the water balance through `WaterRuntime`, but not as
preferential flow. The Ksat factor is driven by aggregation (`agg_state.macro`),
not by biopores. Porosity comes from `effective_porosity()`, which is total
porosity minus cryptoporosity (#289). Biopore donation takes from crypto
first, so it can raise that cap by at most the biopore volume fraction, about
0.0015 m³/m³ at 500 pores/m². That made no measurable difference. On
`clay_loam_temperate` and `clay_temperate`, ten days of 40 mm/day gave the same
deep drainage and profile water to 1e-6 mm at 0, 80 and 500 pores/m², measured
at bb276b4.

## Decision

**Preferential flow is modelled structurally but not hydrologically.**

- *Structural (kept).* The pore network (`PoreNetworkModule`) partitions
  porosity into macro, meso, micro and crypto pools. Biopores (ADR-009) form
  from root turnover, decay over time, are destroyed by tillage, and donate
  their volume into the macropore pool. This structure is computed, persisted
  and reported by the API, but no flux reads the partition. Gas diffusion
  (ADR-010) uses total porosity, which the partition and the donation
  conserve, so neither macropores nor biopores change aeration, O₂ or Eh.
  The only partition-sensitive reader is the effective-porosity cap
  described under Context, which made no measurable difference.
- *Hydrological (not modelled).* There is no infiltration bypass, no fast
  drainage path to depth, and no macropore solute transport. Water and nitrate
  move only through the cascading bucket and its `WaterDrained` events.

Removed in #466:

- `agrogame/soil/water/models/dual_porosity.py` (`DualPorosityParams`,
  `DualPorosityWaterModel`, `partition_flow`) and
  `agrogame/soil/water/models/dual_porosity_exchange.py`, together with their
  re-exports from `agrogame.soil.water`.
- The `PreferentialFlowOccurred` event.
- The macropore water domain: `SoilWaterState.theta_macro` and
  `SoilWaterState.enable_dual_porosity()`.
- The `SoilSnapshot.water_theta_macro` field. It is no longer written.
  `SoilSnapshot.from_dict` reads keys explicitly, so older saves that still
  contain the key load and ignore it (ADR-001). This is pinned by
  `tests/test_save_load.py::TestRetiredMacroDomainSnapshotField`.
- `tests/test_dual_porosity.py` and the realism tests
  `test_dual_porosity_heavy_rain_bypass` and
  `test_dual_porosity_light_rain_no_bypass`. These are the only test deletions
  authorised. `test_heavy_rain_on_clay_bypass_visible_in_pore_chain`, which
  asserts only pore-chain bounds, was renamed to
  `test_heavy_rain_on_clay_keeps_pore_chain_bounds_coherent` with its
  assertions unchanged.

Kept: `DailyDrivers.rainfall_intensity_mm_hr`. It has no consumer now, but it is
the input #485 needs.

### Why: three findings

Do not re-implement the retired model as it stood. Wiring it in would not have
produced preferential flow, for three reasons.

The #466 refinement measured each model on a fresh orchestrator's initialised
profile and pore state, for one day with no evaporation, starting from
identical copies of the water state. The table reproduces exactly at bb276b4
(depths in mm):

| preset, rain | intensity | cascading deep / runoff | dual-porosity deep / runoff |
|---|---|---|---|
| clay_temperate, 40 mm | None (production path) | 19.6 / 20.4 | 19.6 / 20.4 |
| clay_temperate, 40 mm | 10 mm/h | 19.6 / 20.4 | 8.9 / 0.7 |
| clay_temperate, 80 mm | 20 mm/h | 23.8 / 56.2 | 18.1 / 0.7 |
| loam_temperate, 60 mm | 15 mm/h | 31.3 / 28.7 | 24.9 / 11.1 |

1. **The model was inert on the production path.** Nothing sets
   `DailyDrivers.rainfall_intensity_mm_hr`, so intensity fell back to
   `rain / 24`. Bypass needed intensity above `0.6 × Ksat_top` (the
   `bypass_threshold_factor`, Jarvis 2007, 0.5 to 0.8). That threshold is
   57.6 mm/day on `clay_temperate` (Ksat_top 4 mm/h) and 72 mm/day on
   `clay_netherlands` (5 mm/h). Below those amounts the two models give
   identical results (row 1). A sub-daily intensity disaggregation is new
   science that needs its own citation. The SWAT α₀.₅ half-hour peak fraction
   (Neitsch et al. 2011, SWAT Theoretical Documentation, §2:1.3) is a
   candidate.
2. **When it fired, deep drainage fell instead of rising.** The routing filled
   macropore storage top-down from layer 0, which holds about 61 mm on
   `clay_temperate`. The first-order exchange (α_w = 0.2 d⁻¹) then returned the
   water to the matrix. Water parked near the surface instead of bypassing to
   depth. Deep drainage dropped from 19.6 to 8.9 mm, from 23.8 to 18.1 mm, and
   from 31.3 to 24.9 mm (rows 2 to 4). The fall in runoff is physically
   plausible. The fall in drainage is the opposite of what macropore flow does
   in structured clay (Beven & Germann 1982; Jarvis 2007).
3. **Bypass water carried no nitrate.** Macropore routing and exchange emitted
   no `WaterDrained`. `NitrogenCycle._on_water_drained` is the only NO₃
   transport path, so rain diverted from the matrix *lowered* nitrate leaching.
   Macropore solute transport would be needed, for example MACRO's
   mixing-depth inflow concentration (Larsbo & Jarvis 2003, MACRO 5.0 technical
   description). That is new science too.

Wiring the model in as it stood would therefore have forced a recalibration of
water-balance and leaching bounds (for example
`test_seasonal_no3_leaching_contrast_and_band` and the Sahel bound relaxed in
#458) and of clay-preset yields. That work would have served a model whose
drainage and leaching move in the wrong direction.

### Approvals

All three come from Edwin de Jong, 2026-10-02, relayed via the manager
session and recorded in #466:

- Option B (retire) was chosen over Option A (wire in and recalibrate).
- Deleting the tests listed above was explicitly authorised.
- This ADR was explicitly approved.

The #466 PR carries a merge hold: Edwin merges it, not an agent.

### Path back

The capability continues as **#485 (Preferential flow v2)**, phase 3 of the
roadmap in #476. Its acceptance criteria are the three findings above:

1. sub-daily rainfall intensity;
2. routing that bypasses to depth;
3. macropore solute transport.

The recalibration and a new ADR superseding this one come after those. The
retired code can be recovered for reference with
`git show bb276b4:agrogame/soil/water/models/dual_porosity.py`. Do not restore
it as-is, for the reasons above.

### Amendments to ADR-010

- *Context*: the #213 entry is marked as retired, and the "wiring is
  intentionally deferred" sentence now points here.
- *Consequences → Easier*: the "realism follows physics" bullet no longer
  claims that heavy-rain bypass surfaces in simulation outputs. The snapshot
  bullet no longer lists `water_theta_macro`.
- *Consequences → Harder* and *Follow-ups*: the "DualPorosity is still not
  opt-in" item and the "DualPorosity config flag" follow-up are replaced by a
  pointer to this ADR and #485.

## Consequences

### Easier

- No module, event or ADR claims hydrological behaviour that the running
  simulation does not have.
- One water model. Nothing in the water balance carries a dormant second
  domain.
- The change is numerically inert. Two seasons of maize on `clay_temperate`
  and on `loam_temperate`, including `reset_crop` and a JSON save/restore
  between seasons, give identical yield, biomass, deep drainage, runoff and
  NO₃ leaching before and after (max |Δ| = 0 over every compared scalar, at a
  1e-9 tolerance). No realism bound, crop parameter, preset or calibration
  value moved.

### Harder

- Clay presets under-represent rapid drainage and nitrate bypass after heavy
  storms on structured soil. Biopores have no measurable consequence for
  water, aeration or rooting; they change only the reported pore-network
  partition (see Decision). The hydrological gap is tracked in #485.
- `DailyDrivers.rainfall_intensity_mm_hr` is accepted but read by nothing until
  #485 lands.
- Saves written before #466 carry an ignored `water_theta_macro` key. It is
  dropped on the next save.

## Alternatives Considered

### Option A: wire it in and recalibrate

Rejected on the three findings above. Wiring alone changes nothing on the
production path (finding 1). Once intensity exists, the model moves drainage
and leaching in the wrong direction (findings 2 and 3). Fixing that is a
multi-issue science programme, now #485, and not a wiring task.

### Keep the module dormant and fix only the documentation

Rejected. Dormant code with literature citations, unit tests and a passing
realism test looks like a quick win: "just wire it in". That is the trap this
ADR records. The code would also keep a second water domain and a snapshot
field alive for no running behaviour.

### Opt-in config flag (ADR-010's follow-up)

Rejected for the same reason. A flag would offer players and calibration runs a
mode whose drainage and leaching move in the wrong direction.

## References

- Issue #466: wire or retire (this decision); the tech-refinement comment holds
  the side-by-side analysis.
- Issue #485: Preferential flow v2 (the path back). Issue #476: roadmap.
- Issue #213: original dual-porosity delivery. Issue #74: pore-network
  umbrella. Issue #289: effective porosity from the pore network.
- ADR-001: save format and backward compatibility. ADR-009: biopore
  calibration. ADR-010: pore-chain phase ordering (amended).
- Beven, K. & Germann, P. 1982. Macropores and water flow in soils. *Water
  Resour. Res.* 18(5): 1311–1325.
- Jarvis, N.J. 2007. A review of non-equilibrium water flow and solute
  transport in soil macropores. *Eur. J. Soil Sci.* 58: 523–546.
- Gerke, H.H. & van Genuchten, M.Th. 1993. A dual-porosity model for
  simulating the preferential movement of water and solutes in structured
  porous media. *Water Resour. Res.* 29(2): 305–319.
- Ahuja, L.R. et al. 2000. *Root Zone Water Quality Model.* Water Resources
  Publications.
- Larsbo, M. & Jarvis, N. 2003. *MACRO 5.0: a model of water flow and solute
  transport in macroporous soil. Technical description.* Swedish University of
  Agricultural Sciences, Emergo 2003:6.
- Neitsch, S.L. et al. 2011. *Soil and Water Assessment Tool Theoretical
  Documentation, Version 2009.* Texas Water Resources Institute TR-406.
