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
related_adrs: [ADR-002, ADR-006, ADR-020]
---

# Soil

Umbrella for the soil-side science modules. Each subdomain lives in its own
package with the canonical `params/state/module/runtime/events` shape (see
`docs/conventions.md` §1).

## Sub-packages

| Package | Purpose | Page |
|---------|---------|------|
| `agrogame.soil.water` | Water balance (cascading bucket) | [water.md](water.md) |
| `agrogame.soil.nitrogen` | N cycling (mineralization, nitrification, leaching) | [nitrogen.md](nitrogen.md) |
| `agrogame.soil.canopy` | Canopy light interception and biomass | [canopy.md](canopy.md) |
| `agrogame.soil.phenology` | GDD-driven crop phenology | [phenology.md](phenology.md) |
| `agrogame.soil.som` | Three-pool SOM (RothC) | [microbial.md](microbial.md) |
| `agrogame.soil.microbes` | Microbial biomass and activity | [microbial.md](microbial.md) |
| `agrogame.soil.redox` | Redox dynamics (Eh, dominant acceptor) | [soil-gas-redox.md](soil-gas-redox.md) |
| `agrogame.soil.micronutrients` | Fe/Zn/Mn availability | [soil-gas-redox.md](soil-gas-redox.md) |
| `agrogame.soil.aggregation` | Macro/meso/micro aggregate dynamics | — |
| `agrogame.soil.biopores` | Persistent root-channel macropores | — |
| `agrogame.soil.pore_network` | Pore-network capacity (porosity, connectivity) | — |
| `agrogame.soil.gas_diffusion` | O₂/CO₂ transport through pore network | [soil-gas-redox.md](soil-gas-redox.md) |
| `agrogame.soil.phosphorus` | Phosphorus pool dynamics | [phosphorus.md](phosphorus.md) |
| `agrogame.soil.sulfur` | Sulfate, adsorbed and organic S pools | [sulfur.md](sulfur.md) |
| `agrogame.soil.chemistry` | Per-layer pH: N-cycle proton budget, lime | [ADR-020](adr/ADR-020-soil-ph-proton-budget.md) |

## Liming and pH management (#465)

`lime` is a player action: `POST /games/{id}/action` with
`params = {"amount_kg_ha": <float>, "layer": <int, default 0>}`, previewable
through `/action/preview` for the identical cost. It is deliberately **not** a
`_FERTILIZER_TYPES` entry — lime supplies no limiting nutrient — so
`FullSimulationOrchestrator.apply_lime` emits `LimeApplied` and
`ChemistryRuntime` stays the single path into `SoilChemistryModule`.

The pH rise depends on the layer's **pH buffer capacity** (pHBC), derived from
its clay and organic-carbon content:

```
pHBC [cmol(H+)/kg/pH] = 8.5 * clay% / (25 + clay%) + 0.6 * OC%
lime requirement [kg CaCO3/ha per pH unit]
        = pHBC * 0.01 [mol/cmol] * 50 [g CaCO3 per mol charge]
          * soil mass [kg/ha] / 1000
```

Measured pHBC of mineral soils is ~1-2 cmol(H+)/kg/pH on sands, ~3-5 on loams
and ~5-8 on clays, rising with both clay and organic carbon (Curtin & Rostad
1997, *Can. J. Soil Sci.* 77:621-626; Aitken & Moody 1994, *Aust. J. Soil Res.*
32:975-984). The 50 g CaCO3 per mol of charge is stoichiometric; the
buffer-method basis for lime requirement is Shoemaker, McLean & Pratt (1961),
*SSSAJ* 25:274-277. The three coefficients above are **calibrated** so every
shipped preset lands inside the published band for its texture class — they are
not a published regression.

For the shipped presets this gives a layer-0 lime requirement of roughly
2.6 t/ha per pH unit on `sandy_arid`, 8.5 t/ha on `loam_temperate` and
13.6 t/ha on `clay_temperate`. Those read high against textbook tables only
because the model's layer 0 is 25-30 cm while published tables assume a
15-20 cm plough layer; per unit soil mass they sit inside the published band.

Not modelled here: gradual dissolution over weeks (#482 — no citable day⁻¹
rate constant exists; see Barber 1984) and per-preset initial pH (#481 — every
preset currently starts at a flat 6.8).

## Soil acidification: the N-cycle proton budget (#492)

Soil pH moves with the H+ that the nitrogen transformations release, not with
time ([ADR-020](adr/ADR-020-soil-ph-proton-budget.md)). Per mol N (Bolan,
Hedley & White 1991, *Plant Soil* 134:53-63; Helyar & Porter 1989): urea
hydrolysis and ammonification -1, nitrification +2, NO3 uptake -1, NH4 uptake
+1, denitrification -1, NH3 volatilisation +1. Leaching needs no term: the
acidity stays where the nitrate was made. Each layer's net H+ is released once
a day at `DayTick(day_end)` as `ProtonLoadOccurred`, and urea's hydrolysis
term at application, so nothing is pending across a step, `reset_crop` or save.
`SoilChemistryModule.apply_proton_load` converts it with the buffer capacity
above:

```
dpH = -H+ [kmol/ha] / (pHBC [cmol/kg/pH] * soil mass [kg/ha] / 1e5)
```

So urea nitrified and taken up by the crop is pH-neutral, nitrate left in or
leached from the soil acidifies by one H+ per N, and unfertilised soil barely
moves. On `loam_temperate` at 200 kg N/ha layer 0 falls about 0.036 pH per
150-day season (0.47 mol H+ per mol urea-N, the efficient end of Goulding
2016, *Soil Use Manage.* 32:390-399); sand falls faster and clay slower. The
three former proxies (a fixed P-fixation clock, a per-event leaching step and
an acidifying-fertiliser event nothing emitted) are gone. The weak daily
relaxation toward 6.8 remains until #481 removes it.

## Notes

Several sub-packages are still pre-canonical (`*Runtime` not yet
orchestrator-wired) — see `docs/conventions.md` §1 "Documented exceptions"
for the current state. Wiring deferred to **#284**.
