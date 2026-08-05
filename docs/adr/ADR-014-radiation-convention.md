# ADR-014: Canonical shortwave-radiation convention at the day-tick boundary

## Status

<!-- One of: Proposed | Accepted | Deprecated | Superseded by ADR-YYY -->
Accepted — PO decision is **A2**: adopt the physical per-PAR RUE basis and
recalibrate the crop set (biomass output is allowed to shift). See Decision
Part 3; the zero-regression relabel is recorded as the rejected alternative A1.

## Context

The daily simulation driver carries a single radiation field, `par_mj_m2`, on
the `DayTick` passed into `Orchestrator.step_day`. Two independent consumers
read it, and **four entry points populate it with two incompatible conventions**.
The result is that reference ET is overestimated ~2–4× (issue #414) while crop
biomass happens to land in a realistic range only because a second error
compensates for the first (issue #418). This ADR fixes the meaning of the
boundary field once, so both consumers can be made physically correct.

**The single field, two meanings.** What flows into `par_mj_m2` today:

| Entry point | Value fed | Convention |
|-------------|-----------|-----------|
| `agrogame/game/turn.py:126` (the real game loop) | `rec.shortwave_mj_m2` | raw shortwave **Rs** |
| `agrogame/api/routes.py:374,868` | `rec.shortwave_mj_m2` | raw shortwave **Rs** |
| `agrogame/sim/engine.py:216` | `(net_radiation or shortwave) * 0.48` | ~PAR, and double-discounted onto net radiation |
| `agrogame/cli.py:43` | `(shortwave or net_radiation) * 0.48` | ~PAR (0.48·Rs) |

**The two consumers, each applying its own wrong conversion:**

- **ET side** — `ETRuntime._resolve_climate` (`agrogame/atmosphere/et/runtime.py:75`)
  sets `net_radiation = par_mj_m2 / 0.48`, i.e. it *treats the field as PAR and
  back-converts to net radiation*. Fed raw shortwave (the live game path), this
  yields `Rn = Rs / 0.48 ≈ 2.08·Rs`. FAO-56 net radiation for a green crop is
  `Rn ≈ 0.5–0.6·Rs`, so ET0 runs ~3.5–4× high (this is #414). Fed the `0.48·Rs`
  path, it yields `Rn ≈ Rs` — still ~2× high.

- **Biomass side** — `Orchestrator.step_day` forwards `par_mj_m2` as
  `incident_par_mj_m2` into the canopy, where biomass growth is
  `RUE × intercepted_radiation`. The RUE presets are documented as *per MJ
  intercepted PAR* (`agrogame/params/canopy.py:19`, `agrogame/params/models.py:45`)
  but are fed raw shortwave on the live path. Maize base RUE is `3.56 g/MJ`
  (`data/crops/presets.yaml:23`), which reads like the C4 vs-PAR literature
  figure (~3.3–4.0 g/MJ; Kiniry 1989, Sinclair & Muchow 1999) but is applied to
  *shortwave* (≈2.08× PAR), over-counting absorbed radiation ~2×. Note `3.56` is
  a clean literature value in **neither** basis: it is labelled and sized like a
  vs-PAR RUE, yet used as a vs-shortwave one (the true vs-shortwave maize figure
  is ~1.6–1.7 g/MJ). It is best understood as a calibrated posterior, and
  realistic biomass currently depends on that shortwave over-count.

**The load-bearing constraint (why #418 is not a one-liner).** For maize you
cannot simultaneously hold all three of: (a) a true 0.48 shortwave→PAR fraction,
(b) literature per-PAR RUE (~3.3–4.0), and (c) today's realistic biomass.
`biomass ∝ RUE × radiation`; moving from `3.56 × Rs` to `3.56 × 0.48·Rs` **halves**
maize biomass. Whether biomass output is allowed to shift is a product decision,
not an engineering one — which is why #414/#418 were escalated here rather than
auto-implemented.

A physically correct radiation pattern **already exists in this repo**, which is
strong evidence the live path is simply inconsistent, not intentionally different:
`agrogame/api/forecast.py:50` uses `_NET_RAD_FRACTION = 0.6` as
`priestley_taylor(t, 0.6·Rs)` (`forecast.py:445`) — `Rn ≈ 0.6·Rs`, in the FAO-56
range. A tested helper `net_radiation_from_shortwave(rs, albedo)` exists
(`agrogame/weather/utils.py:27`) with `DEFAULT_ALBEDO = 0.23`
(`agrogame/weather/constants.py:20`), returning `(1 − albedo)·Rs`. (Note:
`agrogame/api/dashboard_facade.py:217` is *less wrong* but not a model to copy —
it avoids the `/0.48` inflation yet still feeds a raw `Rn ≈ Rs`, ~2× the physical
value; only `forecast.py` is genuinely correct.)

## Decision

Nail down one convention at the boundary and make each consumer physically
correct against it. Three parts:

### 1. The day-tick radiation field carries incoming shortwave **Rs**

The driver value is **incoming shortwave irradiance Rs (MJ m⁻² d⁻¹)** — the
quantity the weather layer actually produces. Rename the field from `par_mj_m2`
to `shortwave_mj_m2` (with a compatibility shim during migration, per the
project's rename discipline). All four entry points feed **raw Rs**: remove the
stray `* 0.48` in `sim/engine.py:216` and `cli.py:43` so they match
`game/turn.py` and `api/routes.py` (the live game path is already correct;
`engine`/`cli` are the outliers, and `engine`'s preference for
`net_radiation_mj_m2` is a double-discount that also goes away).

### 2. ET derives net radiation from Rs (fixes #414)

`ETRuntime._resolve_climate` stops computing `Rs/0.48` and instead derives net
radiation as a fraction of shortwave that lands in the FAO-56 range. The
**primary** approach reuses the constant the repo's already-correct forecast
path uses: `Rn = _NET_RAD_FRACTION · Rs` with `_NET_RAD_FRACTION = 0.6`
(`agrogame/api/forecast.py:50`) — a single lumped net-radiation fraction that
bakes in albedo and typical net longwave, giving `Rn ≈ 0.6·Rs`, squarely in the
`0.5–0.6·Rs` target. Promote that constant to a shared location so ET and the
forecast agree.

An albedo-only reduction (`net_radiation_from_shortwave(Rs, 0.23) = 0.77·Rs`)
is **not** sufficient on its own — at `0.77·Rs` it still leaves ET0 ~40% high,
above this ADR's own net-radiation invariant — because it omits net longwave.
The physically explicit alternative is the full FAO-56 `Rn = (1−α)·Rs − Rnl`
(Eq. 40); it is deferred because the longwave term needs humidity `ea` and
clear-sky `Rso` (latitude, day-of-year), which the `DayTick` does not resolve
today. The `0.6·Rs` lumped fraction is the pragmatic in-range choice until those
inputs are wired.

The seasonal actual-ET bands added in #332 (`[350,650]` NL, `[550,950]` Kenya)
were tuned with inflated ET0 masked by supply/demand clamps and **must be
re-baselined** as part of this work.

### 3. RUE adopts the physical per-PAR basis; the crop set is recalibrated (A2)

Apply the shortwave→PAR fraction on the biomass side — intercepted PAR
`= f_PAR · (1 − e^{−k·LAI}) · Rs` with `f_PAR = 0.48` — and re-anchor every crop's
`rue_g_per_mj` to the **vs-intercepted-PAR literature basis** (C4 maize ~3.3–4.0;
C3 cereals, legumes, and the other presets to their respective literature
ranges), with the docstrings now truthfully reading "per MJ intercepted PAR".
This is physically honest and makes RUE directly comparable to DSSAT/APSIM.

The consequence is deliberate and **accepted**: because `biomass ∝ RUE × PAR`,
moving maize from `3.56 × Rs` to `~3.5 × 0.48·Rs` **roughly halves raw biomass**.
The model is therefore **recalibrated as a campaign**, not patched. With
radiation and RUE now physically correct, the biomass/grain/LAI the model
produces is re-validated against **independent literature yield ranges**, and the
levers that were masked by the 2× radiation over-count — light-extinction `k`,
maintenance respiration, partitioning / harvest index, N limitation — are
re-tuned per crop until outputs land in literature. Every biomass, grain, LAI,
ET, and leaching bound in `tests/integration/test_realism.py` is re-derived, and
the crop preset comments (`# NL posterior`, `# APSIM typical`, …) are updated to
cite the new basis.

The calibration target is **literature agreement, not restoration of the
pre-fix numbers.** Re-hitting the old yields by fudging other levers would
re-introduce the very compensation this ADR removes; if the physically-correct
model under- or over-predicts, that is a real finding about the other levers, to
be resolved on its merits.

Because applying `f_PAR` breaks realism the instant it lands, this is **not
incrementally shippable on `main`**: the boundary change (Part 1), the ET fix
(Part 2), the RUE re-anchor, and the per-crop recalibration land together on a
campaign branch (or behind a flag), gated on the full realism suite passing
against the re-derived literature bounds.

## Consequences

**Easier / fixed:**
- Reference ET0 returns to the FAO-56 range; ETc, water-stress onset (Ta/Tp),
  drainage, and drought-limited yields become physically credible instead of
  compensating for a 2–4× inflation.
- One documented meaning for the radiation driver; the `forecast.py` /
  `dashboard_facade.py` path (already correct) and the live path stop
  disagreeing.
- RUE presets stop claiming a per-PAR basis the code does not honour.

**Harder / follow-up work:**
- **A2 is a recalibration campaign, not a patch, and cannot ship incrementally
  on `main`.** Applying `f_PAR` halves raw biomass on day one; the boundary
  change, ET fix, RUE re-anchor, and per-crop re-tune must land together on a
  campaign branch behind the realism-suite gate. Sequenced phases:
  1. **Convention + ET (Parts 1–2).** Standardise the boundary on raw Rs, fix
     `ETRuntime` to `Rn = 0.6·Rs`, promote `_NET_RAD_FRACTION` to shared. ET0
     drops to band; re-baseline the #332 ET/leaching bounds. (This slice is
     independently correct and could even land first, since ET and biomass are
     separate consumers — but under A2 it is the campaign's first commit.)
  2. **PAR fraction + RUE re-anchor.** Introduce `f_PAR` at the interception
     boundary; set all 9 RUE presets to vs-PAR literature with citations;
     correct the docstrings. Biomass roughly halves here — realism red until
     Phase 3.
  3. **Per-crop yield recalibration.** Re-tune `k` / respiration / HI / N per
     crop against literature yield ranges; re-derive every biomass/grain/LAI
     bound in `tests/integration/test_realism.py`. The repo's
     `scripts/bayesian_calibration.py` + `data/.../scenarios.yaml` are the
     calibration harness; this is the large, iterative phase.
  4. **Validation + docs.** Full realism suite green against re-derived bounds;
     document the convention in `docs/configuration.md` / `docs/conventions.md`.
- The rename `par_mj_m2 → shortwave_mj_m2` touches the `DayTick` contract and
  every entry point; do it with a compatibility shim and a golden/wiring check,
  consistent with the `daily_step` rename work (#282/#411).
- Expect crop **yields to move** relative to today. Under A2 that is intended:
  the pre-fix numbers were partly an artefact of the 2× radiation over-count.

**Invariants after this ADR:**
- The day-tick radiation field is **incoming shortwave Rs**, fed raw by every
  entry point. Every physical reduction is applied *inside* the consumer: ET
  derives `Rn ≈ 0.6·Rs`; biomass derives intercepted PAR via `f_PAR`. No
  fraction is pre-applied at the boundary.
- ET net radiation is `≤ Rs` (physically, `Rn ≈ 0.5–0.6·Rs`) — never `> Rs`.
- RUE presets carry a **true per-PAR** value with a literature citation; the
  biomass path multiplies RUE by intercepted **PAR**, never by shortwave.

**Scope split for implementation:**
- **#414** — Parts 1 (Rs standardisation) + 2 (ET Rn fix) + ET-band re-baseline;
  Phase 1 of the campaign.
- **#418** — Part 3 under A2: PAR fraction + RUE re-anchor + the per-crop yield
  recalibration (Phases 2–3). This is now an L/XL calibration campaign, not a
  doc fix; it should be split into a tracked epic with per-crop sub-tasks.
- **#424** (unrelated method-naming) is not affected.

## Alternatives Considered

- **A1 — Relabel RUE as vs-shortwave, keep the values (zero regression).**
  Correct the docstrings to "per MJ intercepted shortwave (calibrated)", keep the
  current preset numbers, and change no biomass output; #414 (ET) still lands but
  #418 collapses to a docstring/convention fix. **Rejected**: it preserves the
  physics inconsistency it merely renames — RUE stays ~2× the true per-PAR
  literature value and is not comparable to DSSAT/APSIM, and the model keeps
  producing realistic biomass only via the radiation over-count. Chosen against
  by the PO in favour of A2 (physical correctness) despite A1's much lower cost.
  A1 remains the fallback if the A2 recalibration campaign proves intractable
  within the available effort.
- **Per-climate PAR fraction** (vary 0.48 by climate/aerosol). Rejected as
  over-engineering for the current model resolution; a single documented fraction
  is adequate and the boundary now carries Rs anyway.
- **Do nothing / narrow-fix ET only.** Fixing `ETRuntime` without standardising
  the boundary would leave `engine.py`/`cli.py` feeding `0.48·Rs` into a
  now-Rs-expecting ET path, reintroducing a ~2× error on those entry points. The
  boundary convention has to be settled for either fix to be safe.

## References

- Issues: #414 (ET0 net-radiation overestimate), #418 (RUE vs PAR fraction),
  #332 (ET/leaching realism bounds — bands to re-baseline), #415/#372 (Kenya RUE
  recalibration — a shortwave-basis posterior).
- Code: `agrogame/atmosphere/et/runtime.py:75`; `agrogame/game/turn.py:126`,
  `agrogame/sim/engine.py:216`, `agrogame/cli.py:43`, `agrogame/api/routes.py:374,868`;
  `agrogame/params/canopy.py:19`, `agrogame/params/models.py:45`;
  the correct pattern: `agrogame/api/forecast.py:50`,
  `agrogame/weather/utils.py:27` (`net_radiation_from_shortwave`),
  `agrogame/weather/constants.py:20` (`DEFAULT_ALBEDO = 0.23`).
- Science: Allen et al. 1998 (FAO-56, Rn Eqs. 38–40); Monteith 1977 (RUE vs
  intercepted PAR); Kiniry 1989, Sinclair & Muchow 1999 (C4 maize RUE ranges).
