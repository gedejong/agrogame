# ADR-018: Continuous simulation — no automatic season end

## Status

Accepted, 2026-11-18. Edwin decided on 2026-11-17 that the game simulates
continuously (#531), and on 2026-11-18 signed this ADR as drafted in the #531
refinement, with decisions D1 to D4 taken as recommended (ruling on #531).
Amends [ADR-017](ADR-017-in-season-alerts.md) and
[ADR-003](ADR-003-economic-model.md); reaffirms
[ADR-001](ADR-001-game-state-persistence.md) rule 5.

The children of #531 implement it one at a time (see "Decisions and
provenance"). Until each lands, the code on `main` keeps the season behaviour
it replaces.

## Context

The engine began as a season-as-experiment simulator: run one season, read the
yield. The game inherited that model:

- `season_complete = MATURE(first patch) or weather exhausted`. When the first
  patch matured, the season completed for every patch, and slower crops were
  reset unsold at the next rollover.
- A per-season weather window: 200 days on `/step`, 150 on the client's Run
  Season. The two series differed.
- `/start-season` and the `/step` rollover reset crops, the season ledger and
  alert latches, and re-charged seed.
- `GET /report` sold standing grain: first field only, at the first patch's
  price. The client calls it after every Harvest, so harvesting one patch
  sold the others mid-season.
- PR #529 (#518) would have auto-sold every crop at completion and refused
  Harvest afterwards.

In the game a season is not an experiment. Edwin (2026-11-17): "we just
simulate continuously."

## Decision

1. **The calendar runs continuously.** `/step` advances days; nothing completes,
   resets or settles on its own. There is no season number, season phase,
   season length or season result.
2. **Crops have a per-patch lifecycle.** A crop is sown, either at game creation
   for the scenario's crop or by Plant. It grows, matures, and is harvested by
   the player. Harvest finalises the crop in the domain layer (crop history,
   legume N credit) and leaves the patch bare, as `reset_crop(None)` does.
   Plant requires a bare patch.
3. **Run** steps up to 200 days with `stop_on_pause=true`. It stops on an
   interrupting alert: drought or nitrogen (ADR-017), *harvest ready*, or, on a
   bare farm, *sowing time*. Next Day and FF7 are unchanged.
4. **Harvest ready** is an interrupting alert, sent once per patch per crop
   cycle, on the first day the patch's crop is at MATURITY. It obeys ADR-017's
   interrupt spacing. ADR-017's rarity target applies to the stress alerts
   (drought, nitrogen).
5. **Standing past ready costs yield.** A crop-specific, cited loss grows with
   days since harvest ready, after a grace period, and is applied to the sold
   quantity at Harvest. The simulated grain pool is not changed, and nothing
   is ever sold, harvested or destroyed automatically.
6. **Weather** is generated on demand in 200-day chunks. Chunk k comes from
   seed `base_seed + k`, starting at `start_date + 200·k` days. Chunk 0
   reproduces the former single-season `/step` series exactly. A save stores
   the seed, not the series (ADR-001 rule 5).
7. **Economy** (amends ADR-003, Settlement):
   - Revenue arises only at Harvest, at the quarter of the harvest date.
   - A full-field Harvest pays each crop at its own price and product.
   - Seed is charged at sowing, scaled by area.
   - `GET /report` never settles.
   - Ledger entries are dated, and P&L is reported per calendar year and per
     harvest.
   - There is no season reset.
8. **Alerts** (amends ADR-017):
   - Latches and spacing persist.
   - A field's latches re-arm on Plant in that field.
   - Day numbers count from game start.
   - The alert log and `pause_count` cover the game so far.
9. **Session and save** carry no season state. Legacy v1 keys are ignored on
   load. No player save existed when this was decided, so no migration is
   needed.
10. **Out of scope:** the engine's season-scoped validation harness
    (`SimulationEngine.run_season`, `tests/integration/test_realism.py`). A
    season as an experiment remains correct there.

## Decisions and provenance

Edwin's ruling on #531 (2026-11-18, relayed by the manager) took every
recommendation of the refinement:

- **D1 (a), "Run until something needs you".** Decision 3. The cap is 200 days
  because `/step` returns a snapshot per day, and the button is renamed
  **Run**.
- **D2 (a), a cited, crop-specific harvest-delay loss applied at Harvest.**
  Decision 5. The abstracts support a grace period and then a rising loss with
  very different shapes per crop (References), but give no per-week rate. The
  rates must come from the full-text tables, and a sorghum source is still
  missing, so #594 is blocked on that extraction and this ADR fixes no curve.
- **D3, a P&L per calendar year plus a receipt per harvest.** Decision 7.
- **D4, Plant on a standing crop is refused with a 400 ("harvest first").**
  Decision 2. Harvesting an immature crop stays allowed, as the salvage path.
- **D5, sign this ADR as drafted.**
- **E1, NL maize does not reach maturity in the year it is sown**, is a
  calibration question outside this ADR, tracked by #599 (probably through the
  cultivar layer, #469). Until it is settled, no "stalled grain fill" trigger
  stands in for *harvest ready*, and Harvest is always available.

Implementation, by the children of #531 and two related issues. C2 (#537),
C3 (#538) and #525 had merged when this ADR was accepted.

| Child | Issue | Decision | Scope |
|---|---|---|---|
| C2 | #537 | 6 | Run Season drives `/step` only, so the game has one weather series |
| C3 | #538 | 2 | Harvest leaves a bare patch (`reset_crop(None)`) |
| related | #525 | 7 | Plant charges seed scaled by the patch's area |
| C4 | #590 | 4 | The *harvest ready* alert |
| C5 | #591 | 7 | Harvest is the only sale; `GET /report` is a read |
| C6 | #592 | 1, 6, 8 | No automatic season end: continuous calendar, weather chunks, latch re-arm on Plant |
| C7 | #593 | 7 | Dated ledger, calendar-year accounts |
| C8 | #594 | 5 | Harvest-delay losses |
| C9 | #595 | 1 | Retire `/start-season`, `GameTurnManager`, `SeasonPhase`, `SeasonResult` and the dead "Next Season" UI |
| C10 | #596 | 6, 9 | Session and save without seasons; weather regenerated from the seed |
| C11 | #597 | 3 | The *sowing time* stop on a bare farm |
| C12 | #598 | 2 | Plant requires a bare patch |
| related | #494 | 3 | The client's Run: `stop_on_pause`, the stop banner, the rename |

## Consequences

**Positive**
- No crop is reset unsold, and no crop is sold without the player.
- Every crop leaves through Harvest, so crop history and legume N credits always
  apply. #518's adjacent finding dissolves.
- One weather length and one seed path.
- The player chooses sowing dates (for example, winter wheat in autumn, #493).
- Harvest timing becomes a real decision, and grain storage (#473) fits
  naturally.

**Negative**
- About 45 API tests assumed seasons. They are deleted with replacements or
  adapted, child by child.
- Crops that do not mature in the year sown become visible. NL maize, as
  calibrated, matures in May of the following year (E1 in #531, tracked by
  #599).
- The model now meets long standing and fallow periods. Roots grow after
  maturity, there is no establishment failure for out-of-season sowing, and no
  residue is returned at harvest. Each is a follow-up.
- Run returns daily snapshots: about 16 MB per 200 days on three patches. This
  is the reason for the cap.

**Supersedes:**
- ADR-017's "`/start-season` only sets up" and its season-start alert reset;
- ADR-003's "Economy settles at the end of each season", and the #371 note that
  `/report` settles standing grain.

## Alternatives Considered

- **Settle automatically at season completion (#518/#529).** Rejected by Edwin.
  It keeps the experiment boundary and refuses Harvest after it.
- **Auto-harvest at maturity.** Rejected: it removes the timing decision.
- **One season per calendar year.** Rejected: it is still an artificial boundary.
- **A hard harvest deadline** (the crop is destroyed after N days). Rejected:
  the cited literature shows gradual, crop-specific losses.
- **365-day weather chunks.** Rejected: they would change the extremes inside
  days 1-200 and invalidate ADR-017's measured alert table.

## References

- #531 (refinement, measurements and Edwin's ruling), its children #589 to
  #598, #599 (E1), #518 and #529 (closed), #450, #469, #473, #493, #494, #525
- ADR-001 (persistence, rule 5), ADR-003 (economy), ADR-017 (in-season alerts)
- Literature behind decision 5, read as abstracts only (the full texts are
  #594's blocker; the list, with what each abstract supports, is under
  "Design point 2" of the #531 refinement):
  - Thomison, P. R., Mullen, R. W., Lipps, P. E., Doerge, T. & Geyer, A. B.
    (2011). Corn response to harvest date as affected by plant population and
    hybrid. *Agron. J.* 103, 1765-1772. doi:10.2134/agronj2011.0147
  - Huang, H., Faulkner, D. B., Berger, L. L. & Eckhoff, S. R. (2012). Harvest
    date influence on dry matter yield and moisture of corn and stover.
    *Trans. ASABE* 55, 593-598. doi:10.13031/2013.41360
  - Mahoney, K. J., Klapwyk, J. H., Stewart, G. A., Jay, W. S. & Hooker, D. C.
    (2015). Agronomic management strategies to reduce the yield loss
    associated with spring harvested corn in Ontario. *Am. J. Plant Sci.* 6,
    372-384. doi:10.4236/ajps.2015.62043
  - Farrer, D., Weisz, R., Heiniger, R., Murphy, J. P. & Pate, M. H. (2006).
    Delayed harvest effect on soft red winter wheat in the southeastern USA.
    *Agron. J.* 98, 588-595. doi:10.2134/agronj2005.0211
  - Clarke, J. M. (1981). Effect of delayed harvest on shattering losses in
    oats, barley and wheat. *Can. J. Plant Sci.* 61, 25-28.
    doi:10.4141/cjps81-004
  - Wang, Y. et al. (2022). Revealing a significant latent loss of dry matter
    in rice based on accurate measurement of grain growth curve.
    *Agriculture* 12, 465. doi:10.3390/agriculture12040465
