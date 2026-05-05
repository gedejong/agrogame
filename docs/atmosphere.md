---
module: agrogame.atmosphere
doc_type: module
references:
  - "FAO-56 (Allen et al. 1998) — Penman-Monteith reference evapotranspiration"
  - "Priestley & Taylor 1972 — radiation-driven ET"
key_classes: []
key_events: []
primary_tests:
  - tests/test_et.py
  - tests/test_evaporation.py
related_adrs: [ADR-002]
---

# Atmosphere

Atmospheric drivers and reference evapotranspiration. Currently a thin wrapper
that exposes the `et/` sub-package implementing FAO-56 Penman-Monteith and a
Priestley-Taylor fallback.

## Sub-packages

- `agrogame.atmosphere.et` — reference ET (`ETPenmanMonteith`, `ETPriestleyTaylor`)
  and ET module wiring.

See [ET (PT/PM + VPD)](et.md) for the equation reference.

## Public API

The top-level package re-exports nothing today — import directly from
`agrogame.atmosphere.et`. This is tracked as a small cleanup in conventions
audit umbrella **#280**.
