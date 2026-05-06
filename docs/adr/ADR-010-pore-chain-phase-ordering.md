# ADR-010: Pore-chain day-tick phase ordering

## Status

Accepted (#284).

## Context

#211 (PoreNetworkModule), #213 (DualPorosityWaterModel), #215 (BioporeModule), #216 (RedoxModule micronutrients), and #217 (GasDiffusionModule) shipped with correct physics and unit tests but were not constructed in `FullSimulationOrchestrator`. The pore chain was mathematically complete but functionally inert — none of the science affected gameplay or simulation outputs.

#284 wires the four daily-step modules into the orchestrator so they actually execute on each `DayTick`. Three of the four (`PoreNetworkModule`, `BioporeModule`, `GasDiffusionModule`) need to fire **before** the existing water/redox/nutrients phases because their outputs flow into those modules. The dual-porosity water model wiring is intentionally deferred — `WaterRuntime` keeps `CascadingBucketWaterModel` until a config mechanism for opting in lands separately (#303-style design question).

## Decision

### Phase ordering

The `Calendar` already emits `DayTick` events in this order (predates #284):

```
day_start → chemistry → water → redox → plant_structure → et → nutrients → canopy → day_end
```

We use the existing `day_start` and `day_end` phases for the pore chain — no new phase added. Within `day_start`, three runtimes subscribe in this order, and the EventBus dispatches handlers in subscription order:

1. **`PoreNetworkRuntime`** — calls `PoreNetworkModule.compute(profile, agg_state)` to refresh `macro / meso / micro / crypto / connectivity` from texture + aggregation MWD. The compute also resets the biopore module's `last_applied_volume_fraction` baseline so the next donation step contributes the full biopore volume rather than a stale delta.
2. **`BioporesRuntime` (donation handler)** — calls `BioporeModule.update_pore_network(pore_state, profile)`, which donates current biopore volume into `pore_state.macro` (absorbing from `crypto` first, then `micro`, capped by total porosity) and refreshes `connectivity`.
3. **`GasDiffusionRuntime`** — calls `GasDiffusionModule.daily_step(profile, theta, temperature, co2_respiration, pore_state=...)` using the now-refined pore geometry.

Then existing phases run in their established order. Two consumers read the `day_start` outputs:

- **`RedoxRuntime`** (on `redox` phase) reads `gas_state.o2_frac` per layer and passes it as `o2_concentration_frac` to `RedoxModule.daily_step`. When provided, Eh is driven by O₂ rather than the WFPS sigmoid proxy.
- **`NitrogenRuntime`** (on `nutrients` phase) reads `gas_state.anaerobic_microsite_frac` per layer and feeds `1 - microsite` into `NitrogenCycle.set_aerobic_fraction_override` so denitrification responds to actual O₂.

Finally, `BioporesRuntime`'s decay handler runs on `day_end` (existing behaviour from #215).

### CO₂ source-term timing

`GasDiffusionModule.daily_step` needs per-layer CO₂ respiration as the O₂-sink term. The producer is `SOMRuntime`, which fires on the `nutrients` phase — **later** in the same tick. So gas diffusion at day N uses CO₂ from day N-1.

The orchestrator buffers per-layer CO₂ from `CO2Respired` events:

```
day N day_start  : GasDiffusionRuntime reads buffer (= day N-1 SOM CO₂), then resets buffer.
day N nutrients  : SOMRuntime emits CO2Respired; orchestrator accumulates into buffer.
day N+1 day_start: same again.
```

Day 1 starts with a zero buffer, which is correct (no SOM has run yet).

### Why this ordering

| Constraint | Resolution |
|------------|------------|
| Biopore donation must see freshly-computed `macro` | PoreNetworkRuntime fires first on `day_start` and resets the biopore baseline. |
| GasDiffusion uses `macro` for total porosity (`pore_state.macro + meso + micro + crypto`) | Donation completes before gas-diffusion runs. |
| RedoxRuntime is data-driven by `gas_state.o2_frac` | Gas diffusion completes (in `day_start`) before redox phase fires. |
| NitrogenCycle's denitrification needs `aerobic_fraction` | Gas diffusion completes before `nutrients` phase. |
| BioporeModule's daily decay runs on `day_end` (#215) | Stays after donation so steady state reflects net (donation − decay). |
| Cascading water model drains during `water` phase | Doesn't matter for `day_start` reads — gas diffusion uses pre-water theta, which captures saturation events before drainage. |

### Subscription-order sensitivity

Subscription order in `_wire_runtimes` is load-bearing because the EventBus dispatches in that order. The orchestrator's `_wire_runtimes` documents this with a comment block, and `tests/integration/test_realism.py::test_phase_ordering_matters` is the regression guard — it constructs a second orchestrator with `day_start` swapped to fire last via the `Calendar.tick(phases=...)` override and asserts the `pore_state.macro` pool diverges from the canonical run.

### CO₂ buffer ownership

The buffer lives on the orchestrator (`self._co2_buffer`) rather than inside `GasDiffusionRuntime`, because:

- The orchestrator already subscribes to `BiomassAccumulated` for plant-N-demand bookkeeping; `CO2Respired` follows the same pattern.
- Putting the buffer in the runtime would couple it to SOM event types it has no other reason to know about.
- Tests can supply the buffer directly to `GasDiffusionRuntime` via the `co2_respiration_supplier` callable without touching the orchestrator.

## Consequences

### Easier

- **Pore chain is wired and deterministic**: 365-day full step exercises every daily-step module without crashes, NaN, or pore-conservation violations.
- **Realism follows physics, not a sigmoid proxy**: Eh and denitrification respond to actual O₂ rather than WFPS, so heavy-rain bypass, waterlog → anaerobic, and cover-crop biopore dynamics surface in simulation outputs.
- **Performance under budget**: median day step < 10 ms on the 3-layer `loam_temperate` profile (`tests/integration/test_realism.py::test_pore_chain_perf_under_10ms_per_day`). ADR-006's NumPy → Numba → Cython escalation is not needed for this chain.
- **Snapshot persistence covers the new states**: `SoilSnapshot.{pore_network, biopore, gas_diffusion, water_theta_macro}` round-trip with float-tolerance equality, with backward-compat default-init for pre-#284 saves.

### Harder

- **Realism-test drift**: with O₂-driven Eh, deeper layers reach lower Eh than they did under the WFPS proxy because the gas-diffusion solver treats per-layer SOM respiration uniformly, while real soils show 5–10× lower respiration at depth (Kapeluck & Van Cleve 1995). One existing test (`tests/test_api.py::test_step_response_includes_redox_state`) was relaxed from "all layers Eh > 0" to "topsoil Eh > 0" with a comment noting the SOM per-layer calibration follow-up.
- **Phase-ordering fragility**: re-arranging subscription order in `_wire_runtimes` silently breaks the chain. The regression test checks for this, but contributors must not break it.
- **CO₂ buffer is global per orchestrator**, not per layer of state. Acceptable for single-field simulations; multi-field orchestration would need per-field buffers.
- **DualPorosity is still not opt-in** at the config level. A separate issue should design the config flag.

### Follow-ups

- Per-layer SOM respiration calibration (deep layers should respire 5–10× less than topsoil) — would let the `test_step_response_includes_redox_state` constraint return to "all layers aerobic" under well-drained conditions.
- DualPorosity config flag.
- Earthworm-burrow contributions (#76).

## Alternatives Considered

### Add a new `pore_chain` phase between `day_start` and `chemistry`

Rejected as scope creep: requires touching the `Phase` Literal, every existing runtime that does `if ev.phase != "X"`, and every test that constructs a custom phase list. Using `day_start` keeps the diff minimal and the chain is logically a "set up the day's pore geometry" step, which is what `day_start` is for.

### Have `GasDiffusionRuntime` subscribe to `CO2Respired` directly

Rejected: the runtime would then need a private buffer and a "this day vs yesterday" swap mechanism living next to the diffusion solver. The orchestrator's existing buffering pattern (`BiomassAccumulated`) generalises cleanly.

### Run pore-network compute lazily on first read each tick

Rejected: makes the order of subsequent reads load-bearing in non-obvious ways. The eager `day_start` recompute is simpler.

### Default-OFF feature flag during initial rollout

The issue suggested gating the whole pore chain behind a config flag, default OFF, until realism tests had been green for ~1 week. We default-ON because (a) realism tests now guard the chain, (b) default-OFF means CI doesn't actually exercise the new code path, defeating the point of having the integration tests. A future flag can be added if production-mode rollout warrants it.

## References

- Issue #284 — orchestrator wiring (parent)
- Issue #290 / ADR-009 — biopore calibration (hard prerequisite, now merged)
- Issue #211, #213, #215, #216, #217 — modules being wired
- ADR-002 — multi-field architecture (Field → Patch → Orchestrator)
- ADR-006 — performance strategy (10 ms/day budget)
- Reddy & DeLaune 2008 — Eh response to saturation
- Beven & Germann 1982 — preferential flow under heavy rainfall
- Kapeluck & Van Cleve 1995 — depth-stratified soil respiration (cited follow-up)
