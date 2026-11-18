# ADR-019: Shipped climate presets carry cited station monthly normals

## Status

<!-- One of: Proposed | Accepted | Deprecated | Superseded by ADR-YYY -->
Proposed. Edwin ruled D1-D5 on #560 (2026-11-18); this record is accepted before
the first leg (#586, Sahel) merges.

## Context

`SyntheticWeatherGenerator._generate_base` drove temperature and shortwave for
every preset from one sinusoid, `sin(2π/365·(doy − 80))`, peaking about 20 June,
with shortwave fixed at ±30%. The schema requires `annual_temp_amplitude_c ≥ 0`,
so a preset could not even invert the phase. The annual levels were uncited.

The #560 audit compared generator monthly means (seeds 42-46, 2024, extremes on)
with cited station normals. Every shipped preset fails the threshold
(|ΔTav| > 1.5 °C or |ΔSW| > 15% in a crop-season month):

| preset (normals) | worst crop-season errors | annual-level errors |
|---|---|---|
| `netherlands_temperate` (KNMI De Bilt 1991-2020) | May +4.5 °C; Sep −4.9 °C, +37% SW; Oct −6.1 °C, +105% SW | Tmin −2.3 °C; SW +41% (14.0 vs 9.96) |
| `kenya_highlands` (KMD Nyeri, WWIS) | Jun-Aug Tav +1.7 to +2.5 °C, Tmax +4.4 to +5.3 °C, SW +29%; Oct −2.9 °C, −26% SW | Tmin −2.4 °C; SW −12% |
| `sahel_arid` (DMN Niamey, WWIS) | Jun-Aug Tav +3.4 to +4.5 °C, Tmax up to +7.5 °C, SW +39 to +44%; Oct −4.6 °C | Tmin −2.4 °C; SW +10% |

The full month-by-month table is in the #560 refinement, section 2.

## Decision

**(a) Shipped presets carry cited station monthly normals** for Tmin, Tmax and
shortwave, as the optional 12-element arrays `monthly_mean_tmin_c`,
`monthly_mean_tmax_c` and `monthly_mean_shortwave_mj_m2` (#500 AC1). Both the
levels and the seasonal shape come from the station. The generator takes the
day's base value from the entry for its calendar month; scenario modifiers,
daily noise, RH, wind, rain and the extremes injector are unchanged. Each value
is cited in the YAML with source, period and access date; `annual_mean_*` must
equal the array means within 0.05 (loader check).

| preset | temperature | shortwave | leg |
|---|---|---|---|
| `sahel_arid` | DMN via WMO WWIS, Niamey (cityId 327), 1961-1990 | NASA POWER v2.10.1 `ALLSKY_SFC_SW_DWN`, 2001-2020, (13.48, 2.17) | #586 |
| `netherlands_temperate` | KNMI De Bilt (260) daily TN/TX, 1991-2020 | same file, Q | #587 |
| `kenya_highlands` | KMD via WMO WWIS, Nyeri (cityId 2949), 1980-2018 (D2) | NASA POWER, (−0.437, 36.958) | #588 |

**(b) The sinusoid stays only for presets without arrays.** Once all three legs
land, no shipped preset uses it. It is kept, and guarded by a golden test pinned
to **test-local** copies of the three legacy parameter sets
(`tests/test_weather_generator.py`, tolerance 1e-12), so it cannot drift.

**(c) The maize posteriors are not refit here.** AGRO-92/102 (`flowering_gdd`
759/777, `maturity_gdd` 1830/1801, `temp_opt_c` 26.4/24.2) were fitted on the
legacy weather. They stay, guarded by the realism suite; #580 refits them.

**(d) Rulings** (Edwin, 2026-11-18). No crop parameter changes.

| # | test | old | new | leg |
|---|---|---|---|---|
| R1 | `test_winter_wheat_netherlands_spring_start` | `3.0 < lai < 8.5` on final LAI | same bound on peak LAI over the run | NL |
| R2 | `test_maize_kenya_grain_yield` | `400 < grain`, `0.30 < hi` | unchanged; the Kenya leg waits for #432 | Kenya |
| R3 | `test_rice_kenya_best` | `650 < biomass < 1100` | replaced by #495's cold-sterility assertion | Kenya |
| R4 | `test_irrigated_beats_rainfed_in_arid_sahel` | both arms sown 2024-06-01, > 1.3× | both arms sown 2024-11-01 (dry season), > 1.3× unchanged | Sahel |
| T1 | `test_step_response_includes_plant_n_nni` | `nni <= 12.0` | **declined**: stays 12.0; #578 lands before the NL leg | NL |
| T2 | `test_forecast_vs_engine.py` (3 tests) | shipped NL weather | test-local legacy NL preset; assertions unchanged | NL |
| T3 | `test_save_continuation.py` | `rel=0.02`; grain-fill milestone at day 100 | `rel=0.02` unchanged, NL leg held on #577; milestone moves to the first save day with grain fill. **Update 2026-11-18:** #577 closed by #585, so continuation is now exact (`==`) and already runs a De Bilt-normals variant. Only the milestone fixture remains for the NL leg | NL |

R4's rationale: on station normals a June sowing grows through the monsoon,
where a fertilised crop is nutrient- rather than water-limited above about
300 mm of rain (Breman & de Wit 1983, *Science* 221:1341-1347). The lift was
0.96-1.10× in June and is 10.5-23.5× in the dry season (seeds 42-46).

**Interaction with #535** (root-water uptake, approved). It moves water stress
on the same presets, Sahel and Kenya most. Whichever of #535 and a #560 leg
lands second re-measures the affected catalog and realism tables (seeds 42-46).
Realism rulings are confirmed once, after both have landed, not re-anchored
twice.

**(e) Staging.** Three PRs, Sahel → NL → Kenya (D5). The first carries the
monthly path, this ADR, the fidelity test and the docs. Gates as of
2026-11-18:
- the NL leg (#587) waits for #578 and this leg;
- the Kenya leg (#588) waits for #432 and #495.

## Consequences

- Weather now has a citable meaning per preset. A fidelity test holds every
  (year, month) mean to ±0.4 °C and ±max(3%, 0.3 MJ/m²) over three years
  crossing two year seams and 29 Feb, with extremes disabled.
- The extremes injector is now biased: it adds heat on top of normals that
  already contain real heatwaves (#579, about +0.7 to +1.3 °C on Sahel monthly
  Tav). Rain occurrence is unrealistic too (#575). Both were masked before.
- The corrected weather exposes latent model defects: vernalization rate
  (#576), cool-highland grain fill (#432) and pre-emergence N banking (#578).
  #578 gates the NL leg, and #432 and #495 gate the Kenya leg. A fourth,
  save/load divergence (#577), was fixed by #585 on 2026-11-18 and no longer
  gates anything.
- Catalog and realism outputs move on each leg. Each leg re-measures them for
  seeds 42-46 against the refinement; > 5% (maturity ±2 d) goes back to the
  refiner. Regression-matrix anchors move and are re-captured per leg.
- **Known matrix finding, accepted under D1.** `validate_realism_matrix.py
  --no-stress-matrix --climates sahel_arid`, seed 42, sown 2024-06-01:
  - On `sandy_subsaharan`, Sahel sorghum AGB falls from 215 to **177.5 g/m²**,
    below the matrix's diagnostic fail floor of 200. Grain goes from 97 to
    77 g/m².
  - FAIL runs go from 13 to 14.
  - The #560 refinement predicted this: the catalog sorghum on that soil falls
    from 43-110 to 23-60 g/m².
  - No realism test covers it.
  - It is re-checked after #535 (uptake) and #575 (rain occurrence) land.
- New presets (e.g. #449 Iowa) are born on this path.

## Alternatives Considered

- **Shape only** (keep preset annual means, add station anomalies). Rejected:
  the levels stay uncited, and it fails a different set of realism tests (Kenya
  winter wheat vernalizes; Sahel winter wheat exceeds 250 g/m²).
- **Nairobi for Kenya.** Rejected (D2): same realism failures as Nyeri, but 22
  rather than 5 extra matrix FAILs and 12-25 rice frost days.
- **Re-tune the sinusoid** (phase and amplitude per preset). Rejected: one
  harmonic cannot fit a bimodal highland or a monsoon climate.

## References

- Issues: #560 (refinement and rulings), #500 (monthly path), #586/#587/#588
  (legs), #575-#580 (follow-ups), #531 (ADR-018, year seam), #432, #495,
  #535 (uptake), #585 (exact save continuation, closes #577).
- Allen et al. 1998 (FAO-56); Breman & de Wit 1983; Samejima et al. 2020,
  *Plant Prod. Sci.* 23:297-305 (central-Kenya cool season May-September).
