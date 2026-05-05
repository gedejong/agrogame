---
module: agrogame.soil
doc_type: module
references:
  - "DSSAT, APSIM, WOFOST soil submodels"
  - "FAO-56 §3 — soil water balance"
  - "RothC — three-pool SOM (labile/intermediate/stable)"
key_classes: []
key_events: []
primary_tests:
  - tests/test_soil_water.py
  - tests/test_nitrogen.py
  - tests/integration/test_realism.py
related_adrs: [ADR-002, ADR-006]
---

# Soil

Umbrella for the soil-side science modules. Each subdomain lives in its own
package with the canonical `params/state/module/runtime/events` shape (see
`docs/conventions.md` §1).

## Sub-packages

| Package | Purpose | Page |
|---------|---------|------|
| `agrogame.soil.water` | Water balance (cascading bucket, dual-porosity) | [water.md](water.md) |
| `agrogame.soil.nitrogen` | N cycling (mineralization, nitrification, leaching) | [nitrogen.md](nitrogen.md) |
| `agrogame.soil.canopy` | Canopy light interception and biomass | [canopy.md](canopy.md) |
| `agrogame.soil.phenology` | GDD-driven crop phenology | [phenology.md](phenology.md) |
| `agrogame.soil.som` | Three-pool SOM (RothC) | [microbial.md](microbial.md) |
| `agrogame.soil.microbes` | Microbial biomass and activity | [microbial.md](microbial.md) |
| `agrogame.soil.redox` | Redox dynamics (Eh, dominant acceptor) | — |
| `agrogame.soil.micronutrients` | Fe/Zn/Mn availability | — |
| `agrogame.soil.aggregation` | Macro/meso/micro aggregate dynamics | — |
| `agrogame.soil.biopores` | Persistent root-channel macropores | — |
| `agrogame.soil.pore_network` | Pore-network capacity (porosity, connectivity) | — |
| `agrogame.soil.gas_diffusion` | O₂/CO₂ transport through pore network | — |
| `agrogame.soil.phosphorus` | Phosphorus pool dynamics | [phosphorus.md](phosphorus.md) |
| `agrogame.soil.chemistry` | pH and ion balance | — |

## Notes

Several sub-packages are still pre-canonical (`*Runtime` not yet
orchestrator-wired) — see `docs/conventions.md` §1 "Documented exceptions"
for the current state. Wiring deferred to **#284**.
