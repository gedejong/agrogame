# ADR-015: SOM initial pool sizing at the kinetic steady state

## Status

Accepted — 2026-09-07.

## Context

`ThreePoolSOM` (RothC-like labile / intermediate / stable pools,
`agrogame/soil/som/pools.py`) is the engine's only mineralisation source.
Its pools used to be filled from a fixed 5 / 20 / 75 % split of the
profile's organic carbon in every layer, with pool C:N ratios of 12 / 15 / 20.
That split is far from the equilibrium of the module's own rate constants:
with `k_labile = 0.05 /d` a 5 % labile pool decomposes almost completely
within one warm season, so a freshly initialised soil released ~13 % of its
topsoil organic N in the first 150 days (issue #435; ~443–460 kg N/ha per
season on the Kenya loam in the realism sweep against a literature range of
1–4 % of organic N per year, Stanford & Smith 1972). The flush inflated
mineral-N peaks to 180–260 kg/ha in unfertilised runs, drove ~165 kg N/ha of
nitrate leaching on the Kenya loam, fed the redox–iron chain on clay and peat
(ADR-010, `docs/soil-gas-redox.md`), and made season 1 carry ~4.4× the net
mineralisation of season 2. Deep layers were as labile as the topsoil.

A second defect hid the transient: `reset_crop` rebuilt the SOM runtime
through the same factory as `__init__`, which constructed a new
`ThreePoolSOM` from the profile after `restore_soil` had already written the
carried-over pools into the old one. Every season therefore started from
freshly minted pools and repeated the flush.

The kinetics themselves are RothC-defensible and pinned by
`tests/test_som_pools.py` (`test_labile_turnover` and friends); they are not
to be retuned to hide an initial-condition problem.

## Options

1. **Keep a fixed split, hand-tune the fractions.** Cheap, but back-solved
   for one soil and one climate; it drifts as soon as the kinetics, the
   protection factors or the clay content change, and it says nothing about
   depth.
2. **Analytical steady state of the module's kinetics.** With a constant
   fresh-C input *F* the pools settle at `C_lab = F / k_lab_eff`,
   `C_int = h_li F / k_int_eff`, `C_stb = h_li h_is F / k_stb_eff`, where
   `k_*_eff` are the protection-adjusted rate constants for the layer's clay
   content and `h_*` the humification fractions. The shares depend on neither
   *F* nor the environmental factor, so they follow from the parameters
   alone. This is the equilibrium initialisation RothC and Century use
   (Coleman & Jenkinson 1996; Parton et al. 1987).
3. **Spin-up simulation.** Run the module under a prescribed fresh-C input
   and climate until the pools stop changing. Converges to the same numbers
   as option 2 (up to a one-day discretisation offset on the labile pool)
   but needs an equilibrium-forcing specification (input rate, temperature
   and moisture series) and costs start-up time in the API.

## Decision

Option 2, with a depth attenuation, implemented as
`steady_state_fractions(params, clay_pct, mwd_mm)`:

- Shares are proportional to `1/k_lab_eff : h_li/k_int_eff : h_li h_is/k_stb_eff`
  using the same `som_protection_factor` as `daily_step`, evaluated at the
  layer's clay content and zero aggregate protection. On a 22 % clay loam
  this gives ≈2.0 % labile, ≈31.8 % intermediate and ≈66.3 % stable; clays
  hold less labile C because protection slows the slow pools most.
- Fresh-C input declines roughly exponentially with depth (Jackson et al.
  1996; Jobbágy & Jackson 2000) and subsoil carbon persists largely because
  that supply is missing (Fontaine et al. 2007). The labile and intermediate
  shares of a layer are therefore multiplied by
  `exp(-(z_mid - z_mid_topsoil) / fresh_input_efolding_depth_cm)` with a new
  parameter `SOMPoolParams.fresh_input_efolding_depth_cm = 30.0`; the stable
  pool takes the remainder. `<= 0` disables the attenuation.
- Total organic C per layer and the pool C:N ratios (12 / 15 / 20) are
  unchanged, so the standing SOM-C is exactly what the profile prescribes.
- The `ThreePoolSOM` object is a preserved state container: the orchestrator
  hands the existing instance to the rebuilt `SOMRuntime`, so a crop reset
  carries the decomposed pools into the next season (guarded by
  `tests/test_multi_season.py`).

## Consequences

Measured on the loam profile (seed-42 weather, unfertilised):

| Quantity | Fixed split | Steady state |
|---|---|---|
| Standalone module, 17 °C, 60 % WFPS, 150 d: topsoil net mineralisation | 157 kg N/ha (6.8 % of organic N) | 100 kg N/ha (4.3 %) |
| Standalone, season 1 / season 2 net mineralisation | 4.35 | 1.9 |
| Maize NL (2024-04-15, 150 d): topsoil net mineralisation | ≈13 % | 84 kg N/ha (3.6 %) |
| Maize NL: whole-profile net mineralisation, seasons 1 / 2 / 3 | 463 / (pools reset) | 130 / 56 / 52 kg N/ha |
| Maize NL: mineral-N peak | 218 kg/ha | 63 kg/ha |
| Maize Kenya loam: net mineralisation / NO3 leached | 456 / 166 kg N/ha | 149 / 36 kg N/ha |
| SOM-C change, maize NL 150 d | −4.6 % | −1.7 % |
| Realism sweep (270 runs) FAIL / WARN / PASS | 182 / 77 / 9 | 152 / 103 / 13 |

- The ≤ 5 % first-season criterion of issue #435 is met on the warm scenario.
- The "season 1 within ~1.5× of later seasons" criterion is **not** met:
  in-game the ratio falls from ≈4.4 to ≈2.3. The remainder is the labile pool
  draining, because no residue, root-turnover or exudate carbon enters the
  SOM pools during a season (`SOMRuntime` never passes `fresh_c_input`).
  Adding that input path is the follow-up that closes the gap; until then
  the multi-season tests bound the ratio rather than assert equality.
- Unfertilised runs are now N-limited late in the season and in later
  seasons, as a 2 % OM soil without residue return would be. Tests that
  probe plant-side behaviour under adequate supply fertilise explicitly
  (`tests/test_nutrient_demand.py`), and the realism bands for mineral-N
  peaks and biomass are re-anchored to the unfertilised literature range
  rather than to the flush.
- Total organic N shifts slightly (loam profile 6803 → 6557 kg N/ha) because
  carbon moved from the C:N-12 labile pool into the C:N-20 stable pool; the
  organic C stock is unchanged.
- Saved games restore their SOM pools from the snapshot, so existing saves
  keep whatever pools they had; only new games start at the steady state.
- The module's kinetics imply an equilibrium SOC stock per unit input that is
  several times smaller than RothC's, i.e. the intermediate pool turns over
  faster than a real "slow" pool. That is a parameter-realism question for
  the rate constants and humification fractions, not for the initialisation,
  and is out of scope here.

## References

- Coleman, K. & Jenkinson, D.S. (1996). RothC-26.3 — a model for the turnover
  of carbon in soil. In: Evaluation of Soil Organic Matter Models, NATO ASI
  Series I 38, 237–246.
- Parton, W.J., Schimel, D.S., Cole, C.V. & Ojima, D.S. (1987). Analysis of
  factors controlling soil organic matter levels in Great Plains grasslands.
  Soil Sci. Soc. Am. J. 51, 1173–1179.
- Stanford, G. & Smith, S.J. (1972). Nitrogen mineralization potentials of
  soils. Soil Sci. Soc. Am. Proc. 36, 465–472.
- Jackson, R.B. et al. (1996). A global analysis of root distributions for
  terrestrial biomes. Oecologia 108, 389–411.
- Jobbágy, E.G. & Jackson, R.B. (2000). The vertical distribution of soil
  organic carbon and its relation to climate and vegetation. Ecol. Appl. 10,
  423–436.
- Fontaine, S. et al. (2007). Stability of organic carbon in deep soil layers
  controlled by fresh carbon supply. Nature 450, 277–280.
