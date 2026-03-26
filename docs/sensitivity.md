# Parameter Sensitivity Analysis

Morris one-at-a-time screening (Morris 1991) across 18 simulation parameters, using SALib. Identifies which parameters dominate output variance and should be prioritized for calibration.

## Method

- **Morris screening**: N=50 trajectories (950 model runs per scenario)
- **Parameters**: 18 across canopy (9), phenology (3), ET (4), roots (2)
- **Outputs**: final biomass (g/m2), peak LAI, grain yield (g/m2), maturity day
- **Scenarios**: maize x Netherlands temperate, maize x Sahel arid

## Results: Top 5 Parameters Per Output

### Maize x Netherlands Temperate

| Output | #1 | #2 | #3 | #4 | #5 |
|--------|----|----|----|----|-----|
| Final biomass | **rue_g_per_mj** | pt_alpha | temp_opt_c | extinction_k | emergence_gdd |
| Peak LAI | **lai_max** | rue_g_per_mj | sla_m2_per_g | leaf_frac_veg | pt_alpha |
| Grain yield | **rue_g_per_mj** | flowering_gdd | remob_fraction | leaf_frac_veg | pt_alpha |
| Maturity day | **maturity_gdd** | flowering_gdd | extinction_k | vpd_sensitivity | ritchie_coef |

### Maize x Sahel Arid

| Output | #1 | #2 | #3 | #4 | #5 |
|--------|----|----|----|----|-----|
| Final biomass | **rue_g_per_mj** | temp_opt_c | pt_alpha | extinction_k | ritchie_coef |
| Peak LAI | **rue_g_per_mj** | temp_opt_c | sla_m2_per_g | leaf_frac_veg | pt_alpha |
| Grain yield | **maturity_gdd** | rue_g_per_mj | temp_opt_c | remob_fraction | pt_alpha |
| Maturity day | **maturity_gdd** | flowering_gdd | extinction_k | vpd_sensitivity | ritchie_coef |

## Calibration Priority

**High priority** (appear in top 5 across multiple outputs and scenarios):

1. **`rue_g_per_mj`** (Radiation Use Efficiency) — Dominates biomass and grain yield in both climates. Most important single parameter.
2. **`temp_opt_c`** (Optimum temperature) — Strong influence on biomass, especially in heat-limited Sahel.
3. **`pt_alpha`** (Priestley-Taylor coefficient) — Controls ET demand, affects water stress and biomass.
4. **`extinction_coefficient_k`** — Affects light interception; appears in both biomass and phenology outputs.
5. **`flowering_gdd` / `maturity_gdd`** — Phenology timing controls grain fill duration and maturity.

**Medium priority**:

6. `sla_m2_per_g` — Drives LAI from leaf biomass.
7. `leaf_fraction_vegetative` — Affects canopy development rate.
8. `remobilization_fraction` — Important for grain yield.

**Low priority** (safe to leave at defaults):

- `senescence_rate_per_day`, `max_depth_cm`, `growth_rate_cm_per_day`, `stage1_limit_mm`

## Interpretation

- **RUE is the single most important parameter** — a 10% change in RUE has more impact on biomass than a 50% change in root depth.
- **Climate modulates sensitivity**: `temp_opt_c` matters more in Sahel (heat stress), `ritchie_coef` matters more in Sahel (water limitation).
- **Phenology parameters control timing** but have limited effect on total biomass.
- **Root parameters have low sensitivity** — the model is more driven by above-ground processes.

## Reproducing

```bash
poetry run python scripts/sensitivity_analysis.py --trajectories 50 --outdir out/sensitivity
```

Output: CSV files with mu_star/sigma per parameter, tornado plot PNGs.

## References

- Morris (1991): Factorial sampling plans for preliminary computational experiments. *Technometrics*, 33(2), 161-174.
- SALib: Herman & Usher (2017). *Journal of Open Source Software*, 2(9).
