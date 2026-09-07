## Soil gas, redox and micronutrient redox coupling

Three modules form the aeration chain that decides whether a layer is aerobic,
what its redox potential (Eh) is, and whether reduced iron and manganese become
plant-available: `agrogame.soil.gas_diffusion` (soil-air O₂/CO₂ profile),
`agrogame.soil.redox` (Eh, dominant electron acceptor, N₂O partition, CH₄) and
the redox coupling in `agrogame.soil.micronutrients`. The nitrogen cycle reads
the same gas profile for denitrification. Phase ordering is fixed by
[ADR-010](adr/ADR-010-pore-chain-phase-ordering.md).

### Gas diffusion (`agrogame.soil.gas_diffusion`)

- **Problem solved**: a steady-state Fick balance per layer once a day,
  `d/dz (D_eff · dC/dz) = S`, with `C` the soil-air volume fraction of the gas.
  Boundary conditions are the atmosphere at the surface (O₂ 0.2095, CO₂ 0.00042)
  and zero flux at the bottom of the profile. A single-layer profile has the
  closed form `C = C_atm − S·L²/(2·D_eff)`.
- **Diffusivity**: Millington–Quirk relative diffusivity `τ = θ_a^(10/3) / φ²`
  (Millington & Quirk 1961; Moldrup et al. 2000), `D_eff = D_air(T) · τ`, with
  `D_air` scaled from 20 °C by `(T/T_ref)^1.75` (Massman 1998). A floor of
  `1e-5 · D_air` keeps the solver defined in saturated layers.
- **Source term per unit bulk soil**: SOM respiration (kg C/ha/day) is converted
  to mol C/(m² s), spread over the layer's full thickness (mol C/m³ soil/s) and
  multiplied by the molar volume (0.024 m³/mol) to give a fraction/s. The O₂ sink
  is the CO₂ source times the respiratory quotient (1.0). The solver integrates
  `rate × dz` per cell against face fluxes `D_eff · ΔC/Δz`; `D_eff` is a
  bulk-soil diffusivity, so the source must share that basis. Dividing by θ_a
  (a per-soil-air rate) would overstate the demand by 1/θ_a, roughly 5× on clay
  at field capacity.
- **Clamp**: concentrations are clamped to [0, 1]. A negative raw O₂ solution
  means the diffusive supply cannot meet the prescribed sink: the layer is
  anoxic and its respiration would be O₂-limited in reality. The SOM module does
  not receive that feedback, so CO₂ can pin at 1.0 in saturated layers.
- **Anaerobic flags**: a layer is `anaerobic` when O₂ < 0.02 or θ_a < 0.10, the
  critical air porosity below which aeration limits roots and microbes
  (Stepniewski 1994). The `anaerobic_microsite_frac` ramp is 1.0 at O₂ ≤ 0.01,
  falls linearly to 0.0 at O₂ ≥ 0.04 (Arah & Smith 1989). The nitrogen runtime
  feeds `1 − microsite` into `NitrogenCycle.set_aerobic_fraction_override`, so
  denitrification happens only in layers whose bulk soil air is below 4 % O₂.

Worked example, `clay_temperate` at field capacity (θ 0.36/0.35/0.34, φ
0.55/0.54/0.53, θ_a ≈ 0.19), 15 °C, respiration 18/5/2 kg C/ha/day:

| layer | O₂ | CO₂ | anaerobic |
|---|---|---|---|
| 0–30 cm | 0.175 | 0.043 | no |
| 30–65 cm | 0.155 | 0.069 | no |
| 65–105 cm | 0.148 | 0.077 | no |

Aerated cropped topsoil holds ≥ 15 % O₂ and 0.5–5 % CO₂; only flooded or
compacted profiles fall outside (Glinski & Stepniewski 1985). The same profile at
saturation solves to O₂ 0 and CO₂ clamped at 1.0 in every layer.

State: `GasDiffusionState.o2_frac`, `co2_frac`, `anaerobic`,
`anaerobic_microsite_frac` (per layer). Event: `GasConcentrationUpdated`.

### Redox (`agrogame.soil.redox`)

- **Equilibrium Eh from O₂**: log-linear in the soil-air O₂ fraction between
  `o2_anaerobic_frac` (0.002 → `eh_min_mv` −300) and `o2_aerobic_frac` (0.05 →
  `eh_max_mv` 450). The O₂/H₂O couple buffers Eh at aerobic values (Nernst:
  ≈15 mV per decade of pO₂), so Mn, Fe and sulfate reduction need near-complete
  O₂ depletion (Ponnamperuma 1972; Reddy & DeLaune 2008, ch. 4). The mapping is
  a lumped representation of that buffering, not a Nernst equation.

  | soil-air O₂ | ≥ 0.05 | 0.02 | 0.01 | 0.005 | ≤ 0.002 |
  |---|---|---|---|---|---|
  | equilibrium Eh (mV) | 450 | 236 | 75 | −86 | −300 |

- **Relaxation**: Eh decays toward the equilibrium with a first-order time
  constant `tau_days` (2 d), so a layer must stay below ~1 % O₂ for several days
  before Eh crosses the Fe threshold.
- **Fallback without a gas profile**: a sigmoid in water-filled pore space
  (`sigmoid_k` 12, `sigmoid_midpoint` 0.75) between `eh_max_mv` and `eh_min_mv`.
- **Dominant acceptor** (Stumm & Morgan 1996): O₂ above 300 mV, nitrate above
  100 mV, iron above −100 mV, methanogenesis below.
- **N₂O partition**: `n2o_fraction(Eh) = 0.05 + 0.65 / (1 + exp(−(Eh − 50)/80))`,
  ≈0.70 at aerobic Eh, 0.05 at −300 mV (Firestone & Davidson 1989; Weier et al.
  1993). The nitrogen cycle applies it at the layer's bulk Eh. Because
  denitrification is confined to anaerobic microsites, a layer whose bulk air is
  still mostly aerobic partitions near the 0.70 ceiling, which matches the 0.6–0.9
  N₂O share Weier et al. measured at 60 % WFPS; a fully anoxic layer partitions
  at 0.05.
- **Methane**: produced below −200 mV at `ch4_base_rate_kg_c_ha_day` (0.15) scaled
  by severity and a Q10 of 4 (Conrad 2002); an aerobic surface layer oxidises
  `ch4_oxidation_fraction` (0.6) of the upward flux (Le Mer & Roger 2001).

Events: `RedoxChanged`, `N2OEmitted`, `CH4Emitted`, `CH4Oxidized`.

### Micronutrient redox coupling (`agrogame.soil.micronutrients`)

`apply_redox_adjustment(layer, eh_mv)` shifts Fe and Mn between the sorbed and
available pools; the `total` pool is conserved.

- Only the reactive (amorphous oxide) fraction takes part in daily redox
  cycling: `reactive_fe_fraction` 0.02 and `reactive_mn_fraction` 0.05 of the
  total. Crystalline and silicate Fe is inert at these timescales.
- **Reduction** below `fe_reduction_eh_mv` (100 mV; Patrick & Reddy 1976) or
  `mn_reduction_eh_mv` (200 mV; Stumm & Morgan 1996) releases
  `reduction_rate_per_day` (0.02) × severity of the reducible sorbed stock, with
  severity ramping over `severity_span_mv` (200 mV).
- **Re-oxidation** above `reoxidation_eh_mv` (300 mV) precipitates
  `reoxidation_rate_per_day` (0.005) × severity of the available pool.
- Plant response uses DTPA critical levels Fe 4.5, Zn 0.8, Mn 1.0 ppm (Lindsay &
  Norvell 1978) and a toxicity threshold of 300 ppm Fe (Ponnamperuma 1972:
  50–300 ppm Fe²⁺ in flooded soils).

Taken together, iron toxicity needs sustained saturation: bulk O₂ below ~1 % for
days (Eh through 100 mV with `tau_days` 2) and then weeks of release at 2 %/day
of a 2 % reactive ceiling. Clay at field capacity stays at Eh ≈ 450 mV; flooded
rice, peat and irrigated clays that saturate are where the chain engages.

### Known limitations

- **No O₂ feedback on respiration**: the SOM module respires at its aerobic rate
  in anoxic layers, so CO₂ clamps at 1.0 and the anaerobic state persists as long
  as the layer stays wet.
- **Drained soils denitrify nothing**: the gas profile is read at `day_start`,
  after the previous day's drainage to field capacity, and the microsite ramp
  needs bulk O₂ below 4 %. Post-rain anaerobic pulses on loams and sands, and
  aggregate-scale anoxia at high bulk O₂, are therefore absent. The realism
  sweep labels this limitation on its denitrification checks.
- **Root respiration is not part of the gas source**, so low-SOM sands show
  soil-air CO₂ barely above atmospheric.
