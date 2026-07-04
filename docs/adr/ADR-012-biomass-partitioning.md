# ADR-012: Competitive single-pool root/shoot biomass partitioning

## Status

Accepted (#337).

## Context

#330 (PR #336) added a shoot→root allocation so `RootState.biomass_g_m2`
would grow instead of staying structurally zero. The first-pass model was
**additive**: the canopy computed its full daily biomass increment from RUE
and added 100% of it to shoot; roots then received an *extra*
`root_allocation_fraction × increment` bolted on top.

The PO review of #336 measured the consequences on day-150 maize:

- **Total NPP inflated ~10–18%.** Total plant biomass became
  `increment × (1 + f)` — the root mass was created out of nothing rather
  than drawn from a finite pool.
- **Shoot and grain were byte-identical with vs without allocation.** Because
  the shoot increment never saw the root fraction, changing
  `root_allocation_fraction` moved root mass but left shoot/grain untouched —
  there was no source–sink tradeoff. The "partitioning coefficient" was in
  effect an additive root:shoot *ratio*, not a partition.

Established crop models (DSSAT CERES, WOFOST, APSIM) instead treat the day's
assimilate as a **single finite pool** partitioned among organs with fractions
that sum to 1: carbon sent below ground is carbon the shoot does not get.

## Decision

The RUE step's output (`CanopyModule.calculate_biomass_growth`) is the day's
**total assimilate pool** (`gross`). `CanopyModule.daily_step` now partitions
it competitively **before** any leaf/stem/grain split or LAI update:

```
root_frac  = clamp(root_allocation_fraction, 0, 1)
root_inc   = root_frac × gross          # below-ground share
shoot_inc  = gross − root_inc           # = (1 − root_frac) × gross
```

- Only `shoot_inc` grows canopy biomass and feeds leaf/stem/grain and LAI, so
  a higher root fraction **measurably reduces shoot and grain** — a genuine
  tradeoff.
- `shoot_inc + root_inc = gross` every day (Σ fractions = 1), so **roots never
  inflate total NPP**.
- The below-ground share travels on `CanopyFluxes.root_increment_g_m2` and on
  the `BiomassAccumulated` event as `root_increment_g_m2`. The orchestrator
  routes it to the root module; the plant package still needs no
  `soil.canopy` import (the ADR-008 `canopy_increment_provider` port now
  returns the *already-partitioned* root share, so `RootsRuntime` re-applies
  no fraction).
- N/P and micronutrient demand track **total new tissue = shoot + root**
  (= the pool), so demand magnitude is unchanged by the split — only the
  shoot/grain figures move.
- `root_allocation_fraction` stays the frozen `RootParams` source of truth;
  it is wired into the canopy at construction (`CanopyRuntime`) rather than
  duplicated.

### Emergent root:shoot, not tautological

The *standing* root:shoot ratio is an emergent property, **not** the input
fraction: root turnover (0.005/day) trims live root mass while the shoot
carries more standing biomass, so on maize the seasonal ratio settles ~0.15
against an input fraction of 0.18. The realism test asserts the emergent ratio
lands in the cereal 0.1–0.3 band *and* differs from the input fraction, so it
exercises the dynamics rather than echoing an input.

## Consequences

### Easier

- **Physically honest carbon balance.** Total NPP is the assimilate pool; no
  free biomass. Increasing root investment now costs shoot/grain, enabling
  future stress-driven or stage-declining partitioning tables (DSSAT/WOFOST
  FR) to have a real, testable effect.
- **Single point of truth for the split** — the canopy owns it, downstream
  consumers just route the reported shares.

### Harder

- **Shoot/grain figures dropped** by roughly the partition fraction (maize
  shoot ~1711 → ~1168 g/m²; grain ~754 → ~522 g/m²), since assimilate
  previously double-counted into both organs is now split once. Literature
  yield bounds in `tests/integration/test_realism.py` were widened downward
  to bracket the shoot-only output while staying within field AGB/grain
  ranges (total plant biomass shoot + root remains in range). RUE was **not**
  recalibrated — that is a separate calibration decision if the shoot figures
  are judged too low.
- Callers that build `CanopyModule` directly and omit
  `root_allocation_fraction` keep the pre-#337 shoot-only behaviour (default
  0.0), so unit tests are unaffected; only the orchestrated full-sim paths
  change.

## Alternatives Considered

- **Subtract the root share after shoot partitioning.** Rejected: leaf/stem/
  grain and LAI would already have been computed on the full pool, so grain
  and canopy light capture would not feel the tradeoff — the exact bug.
- **Keep partitioning in the orchestrator/roots side.** Rejected: the split
  must happen where the pool is computed and before shoot sub-partitioning;
  doing it after the canopy has grown cannot reduce grain/LAI without undoing
  work.
- **Move `root_allocation_fraction` to `CanopyParams`.** Rejected as
  unnecessary preset churn — it stays in `RootParams` and is wired in.

## References

- DSSAT CERES — daily assimilate partitioned to root/shoot/grain with
  fractions summing to 1 (Jones et al. 2003).
- WOFOST — FR fraction-to-roots table and above-ground partitioning
  (Boogaard et al. 2014).
- APSIM — stage-dependent biomass partitioning among organs.
- Issue #337 — additive-to-competitive partitioning; PO review of #336.
- ADR-008 — import layering / DI port that keeps plant free of `soil.canopy`.
