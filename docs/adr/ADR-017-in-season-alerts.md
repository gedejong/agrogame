# ADR-017: Act any day, with fast-forward interrupted by in-season alerts

## Status

Accepted, 2026-11-17, implemented by #470. Supersedes
[ADR-004](ADR-004-game-loop-turn-system.md), which was never accepted.

Provenance of each decision is recorded under "Decisions and provenance".

## Context

ADR-004 proposed season-based turns: plan before the season, fast-forward
through it, pause on significant events, and revise the remaining plan at each
pause. It stayed `Proposed`, and the game that shipped diverged from it:

- The player acts on any day through `POST /action`: irrigate, fertilise,
  lime, till, plant and harvest. That is close to the "daily turns"
  alternative ADR-004 rejected, except that fast-forward makes the days cheap.
- Days are driven by one loop, `POST /step?days=N` (#487). The client's
  Next Day, FF7 and Run Season buttons all go through it.
- `GameTurnManager.run_season()`, the generator that yielded pauses, ran only
  in its unit tests. `pause_count` was hard-coded to 0 and `pause_events` was
  never appended to. No in-season interrupt ever reached the player.

The refinement of #470 also ran the dead trigger logic on real sessions and
found it unplayable. Sandy NL maize raised 137 pauses in 200 days, 118 of them
consecutive-day N alerts. Every frost pause fell after maturity or with no crop
standing. Drought never fired, not even in the Sahel, because it watched
topsoil θ/FC rather than the plant's own stress. Only the first of three
patches was watched.

## Decision

**The game loop is: act on any day, and fast-forward through days that an
in-season alert can interrupt.** Plan-and-revise is deferred (see
Consequences).

### Detection

`PauseDetector` (`agrogame/game/turn.py`) runs inside `_run_day_step` after
every simulated day, for every field, over all of its patches. A field-level
condition holds when any patch meets it, because irrigation and fertiliser act
field-wide.

Signals are the simulation's own state, never a proxy:

| reason | condition | gate | onset days | re-arm days | interrupts fast-forward? |
|---|---|---|---|---|---|
| drought | Ks < 0.4 | crop emerged and not mature | 2 | 7 | yes |
| nitrogen | N stress < 0.9 | stage ∈ {emerged, vegetative, flowering} | 3 | 10 | yes |
| frost | tomorrow's tmin < the crop's `frost_threshold_c` | stage ∈ {emerged, vegetative, flowering} | 1 | 7 | no, a notice only |

- Ks is the `WaterStressComputed.stress` payload as the canopy receives it:
  Ta/Tp, actual over potential transpiration from supply and demand
  (`water_from_supply_demand`). It plays the role of the FAO-56 water-stress
  coefficient Ks (Allen et al. 1998, ch. 8), which FAO-56 itself derives from
  root-zone depletion. N stress is the graded NNI-based
  `NutrientStressComputed` payload for N (ADR-013).
- The frost gate is `FROST_VULNERABLE_STAGES`, the constant
  `CanopyRuntime._check_frost_damage` itself uses. An alert therefore never
  claims a vulnerability the damage model does not apply.
- The detector reads each patch's per-day event record (`Patch.recorder`,
  re-wired on every crop reset since #402). It subscribes to no bus, so it
  cannot stack handlers across seasons, crop resets or loads (#486), and it
  cannot change a simulated value.

**Latch per (field, reason).** An alert fires once the condition has held for
`onset_days` consecutive days while armed. It then disarms, and re-arms after
`rearm_days` consecutive clear days. A day on which the gate is closed is a
clear day.

**Interrupt spacing.** An interrupting alert does not fire within 3 days of
the previous interrupt on the same field; the gap must exceed 3 days. A reason
held back this way is deferred, not dropped: it fires on the first allowed day
on which its condition still holds. When two reasons become ready on the same
day, drought fires and nitrogen is deferred, so one stop never carries two
interrupts.

**Frost is a notice.** No game action mitigates frost damage yet, so frost is
recorded with `interrupt: false` and never stops fast-forward. Promoting it is
a separate decision, for when a frost-response action exists. #495 may change
the rice case, where chilling injury is being separated from frost.

All thresholds are game-alert parameters (`PauseConfig`). None is a model
constant, and none changes a simulated value.

### API contract

- `POST /step?days=N` steps all N days, as before. With `stop_on_pause=true`
  it stops after the first day on which an interrupting alert fires. The early
  stop is opt-in, so existing clients are unaffected; the client opts in with
  #494.
- `DayResultResponse` gains `pause_events`, `days_stepped`, `days_remaining`
  and `stopped_on_pause`. `PauseEventResponse` gains `field_id` and
  `interrupt`. All new fields have defaults.
- `pause_count` is the number of interrupting alerts this season. `GET
  /status` reports this season's alerts and the live count.
- Latch state and the season's alerts are saved as optional keys within save
  schema v1 (ADR-001). A save without them loads with every reason armed.

## Playtest method and evidence

The thresholds come from a delegated agent playtest (2026-10-02). It drove
real API sessions through `/step`, one day at a time, for all six scenarios in
`game/scripts/scenario_catalog.gd`: tuning seeds 42 to 46, held-out seeds 47
to 51, a 45-config sweep plus validation, about 600 seasons in all. A run with
no recorder gave identical grain and balance. Each config was scored against
three player models: *none*; *respond*, which irrigates 25 mm or fertilises
50 kg urea the morning after a pause; and *random*, which takes the same
actions on random days. An alert is informative when *respond* beats *random*.

**Measured versus assumed.** Every threshold, onset and re-arm value is
measured by that playtest. The rarity target, at most 4 interrupting pauses
per season with a median gap of 14 days or more, is a judgement anchored on
ADR-004's five-minute season, roughly one interrupt per five FF7 presses.
Numbers from playtesting with real players would supersede it.

The implementation reproduces the playtest on the live `/step` path (seeds 42
to 51, one season each, field level):

| scenario | interrupts/season (max) | by reason | min / median gap (d) |
|---|---|---|---|
| NL maize, 3 soils | 1.5 (3) | N 1.0, drought 0.5 | 14 / 20 |
| Kenya maize | 2.8 (4) | drought 1.8, N 1.0 | 17 / 64.5 |
| Sahel sorghum | 1.5 (3) | drought 1.0, N 0.5 | 4 / 31 |
| Kenya rice, clay | 3.1 (4) | drought 2.1, N 1.0 | 11 / 44 |
| NL spring wheat | 1.3 (2) | N 1.0, drought 0.3 | 21 / 27 |
| NL winter wheat | 1.6 (4) | N 1.0, drought 0.6 | 12 / 26 |

The playtest measured a minimum Sahel gap of 2 days, where drought and N onset
fell close together. The spacing rule closes it. Frost notices are about 4 per
Kenya rice season (the playtest measured 3.6) and zero elsewhere.

What the playtest found about the dynamics:

- **Water stress flickers.** Ks < 0.5 episodes last a median of 3 days with a
  median gap of 1 to 2 days. A 7-day re-arm merges most of them; 14 days
  halved the value of responding in Kenya rice, because second dry spells are
  real. An onset of 2 days drops one-day dips that no response can help.
  Ks < 0.3 never fires in NL, and Ks < 0.5 makes the Sahel alert no better
  than random. Ks < 0.4 is the best balance.
- **N stress is persistent.** Once low it stays low for 70 to 150 days, so
  the latch is what makes it one alert. Fertiliser gains 12 to 34% grain
  through vegetative growth, partly in early grain fill, and nothing from
  about 15 days into grain fill, hence the stage gate. A 0.7 threshold misses
  NL spring wheat entirely; 0.8 and 0.9 form a plateau.
- **Frost** gated to the canopy damage stages removes every post-maturity
  alert. NL maize sees sub-zero mornings in grain fill, which the simulation
  correctly does not damage.

Findings that are not threshold problems: Sahel drought is chronic, so an
alert-timed irrigation does no better than a random one; the right response
there is a schedule. Spring-sown winter wheat never vernalises (#493). Kenya
rice's 10 °C threshold is a chilling-injury question for the rice preset
(#495).

## Decisions and provenance

- **Option A: wire the pause system up, redesigned on playtest evidence.**
  #470 refinement, 2026-10-02.
- **Early stop is opt-in on `/step`.** Manager, recorded on #470.
- **One day loop.** `/start-season` only sets up; `/step` drives the days.
  Manager, implemented by #487.
- **Rewrite ADR-004 as a new ADR that supersedes it.** Edwin, relayed by the
  manager.
- **Thresholds delegated to an agent playtest.** Edwin, relayed by the
  manager. Values as in the table above.
- **Drought uses `WaterStressComputed`, as N uses `NutrientStressComputed`.**
  Manager, recorded on #470.

## Consequences

**Positive**

- The player hears about drought and N deficiency when acting still pays, and
  at most a few times a season, rather than never or every day.
- Alerts cannot disagree with the simulation's stress state, and detection
  cannot change a simulated value. `tests/integration/test_pause_dynamics.py`
  checks both, on every catalog scenario.
- There is no game-layer bus subscription left, which closes the class of
  defect #486 fixed.

**Negative**

- Thresholds are tuned to today's crop and climate presets. A recalibration
  that moves Ks or NNI trajectories can change alert frequency; the dynamics
  test is the guard.
- Fast-forward still runs one HTTP call per stop. That is cheap at the
  observed rate of about 1 to 4 stops a season.
- `water_stress` in the day snapshots is the canopy's memory-averaged,
  VPD-scaled growth factor, not Ks, so a drought alert reading "Ks 0.31" can
  coincide with a snapshot showing 0.65. The client banner (#494) should
  quote the alert's own value.

**Deferred**

- **Plan-and-revise.** `ManagementPlan.revise` and `POST /revise` remain, but
  no client path reaches them and no pause offers a revision. Acting on the
  day of an alert replaces it.
- **Client halt and banner**: #494.
- **Frost-response actions**, and with them frost as an interrupt.
- **Season phases.** `SeasonPhase` still reports `planning`, `executing` and
  `settling` as before. #519 tracks `current_day` in `/status`.

## Alternatives Considered

- **Wire the existing generator in unchanged.** Rejected: 137 pauses in a
  season, frost after maturity, no drought, and one patch watched.
- **Retire the pause system.** Rejected: fast-forward without interrupts
  removes the mid-season tension ADR-004 was right to want.
- **Make the early stop the default on `/step`.** Rejected by the manager:
  it changes what existing clients receive, before the client can show why it
  stopped.
- **Subscribe the detector to each patch's bus.** Rejected: every crop reset
  clears the bus (#402), so subscriptions would need re-wiring each season and
  on load, the failure #486 fixed once already. Reading the per-day record
  needs no wiring.

## References

- #470 (this decision), #486, #487, #493, #494, #495, #519
- ADR-001 (persistence), ADR-004 (superseded), ADR-013 (plant-N stress)
- Allen, R. G., Pereira, L. S., Raes, D. & Smith, M. (1998). *Crop
  evapotranspiration*. FAO Irrigation and Drainage Paper 56, ch. 8 (Ks).
