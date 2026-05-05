---
module: agrogame.sim
doc_type: module
references:
  - "ADR-002 — multi-field architecture (Field → Patch → Orchestrator)"
  - "ADR-006 — performance strategy (NumPy → Numba → Cython)"
key_classes:
  - Calendar
  - DayTick
key_events: [DayTick]
primary_tests:
  - tests/test_simulation.py
  - tests/integration/test_full_orchestrator.py
related_adrs: [ADR-002, ADR-004, ADR-006]
---

# Simulation

Composition root for the science engine. Contains the orchestrator that
fires the daily-step phases across soil/plant/atmosphere modules, the
calendar, and the management plan engine.

## Submodules

- `agrogame.sim.calendar` — `Calendar`, fires `DayTick` events.
- `agrogame.sim.calendar_events` — `DayTick` event class.
- `agrogame.sim.orchestrator` — `FullSimulationOrchestrator` wiring all
  domain modules (soil water/N/redox/aggregation/biopores, plant
  phenology/canopy/roots, atmosphere/ET).
- `agrogame.sim.engine` — high-level `SimulationEngine` driving the
  orchestrator over a `WeatherSeries`.
- `agrogame.sim.management` — `ManagementPlan` / `ManagementEvent` (player
  actions scheduled per day).
- `agrogame.sim.builder` — fluent helpers to construct an orchestrator with
  preset crops/soils.

## Notes

`sim/` is intentionally flat (no canonical `params.py` / `state.py` shape) —
it has no domain state of its own. See `docs/conventions.md` §1.
