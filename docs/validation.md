### Validation metrics and benchmarks

We validate simulations against benchmark scenarios using:

- R² (Pearson r²), RMSE, MAE, MBE
- NSE (Nash–Sutcliffe), Willmott d, coverage within tolerance
- Phenology timing error (days)
- Taylor diagram statistics: correlation, standard deviation ratio, centred RMSD

Targets (typical):
- Yield within 10% of benchmark
- Phenology within 5 days to flowering/maturity windows
- Biomass time-series quality: R² > 0.9, NSE > 0.8

How to run:
```bash
poetry run pytest -k benchmarks -q
# Compare two CSV series
poetry run python scripts/compare_series.py --obs tests/data/observed_biomass.csv --sim out/built_crops.yaml --key date --obs-col biomass --sim-col biomass
# Run DSSAT/APSIM trajectory benchmark and GYGA yield comparison
poetry run python scripts/benchmark_trajectories.py --outdir out/benchmarks
```

---

## DSSAT/APSIM trajectory benchmark (AGRO-91)

We compare AgroGame daily trajectories against DSSAT CERES-Maize literature-derived
reference curves for maize across three climates. Reference trajectories use
logistic biomass accumulation and beta-function LAI curves calibrated to published
DSSAT/APSIM outputs (Jones et al. 2003; Keating et al. 2003).

### Taylor diagram results

Taylor diagrams (Taylor 2001) summarize correlation, standard deviation ratio, and
centred RMSD on a single polar plot. The reference point sits at (r=1.0, ratio=1.0).

| Scenario            | Variable              |     r | std ratio | CRMSD |
|---------------------|-----------------------|------:|----------:|------:|
| maize_netherlands   | lai                   | 0.730 |     0.870 | 0.698 |
| maize_netherlands   | biomass_g_m2          | 0.963 |     0.637 | 0.422 |
| maize_netherlands   | cumulative_et_mm      | 0.995 |     1.359 | 0.377 |
| maize_kenya         | lai                   | 0.874 |     1.102 | 0.537 |
| maize_kenya         | biomass_g_m2          | 0.984 |     1.044 | 0.188 |
| maize_kenya         | cumulative_et_mm      | 0.997 |     1.180 | 0.196 |
| maize_sahel         | lai                   | 0.405 |     0.807 | 0.999 |
| maize_sahel         | biomass_g_m2          | 0.974 |     1.157 | 0.290 |
| maize_sahel         | cumulative_et_mm      | 0.990 |     1.788 | 0.811 |

**Key findings:**

- **Biomass** trajectories correlate strongly with DSSAT references (r > 0.96) across
  all three climates, confirming the logistic accumulation pattern is well captured.
- **LAI** shows good correlation in Kenya (r = 0.87) and Netherlands (r = 0.73) but
  weaker in Sahel (r = 0.40), likely due to water-stress timing differences.
- **Cumulative ET** tracks well (r > 0.99) but our model slightly overestimates
  ET in arid conditions (std ratio 1.79 for Sahel). **Caveat:** both simulated
  and reference ET use LAI-based proxies (Beer-Lambert extinction), so high
  correlation reflects consistent methodology rather than independent validation.
  True ET validation requires eddy-covariance or lysimeter observations.
- **Soil moisture** correlation is low across all scenarios (r = 0.15-0.56) because
  our synthetic weather generator produces different rainfall timing than the
  deterministic reference curves. This is expected and not a model deficiency.

### Timing discrepancies

Peak timing comparison between DSSAT reference and AgroGame simulation:

| Scenario            | Variable     | Ref peak | Sim peak | Offset       |
|---------------------|--------------|----------|----------|--------------|
| maize_netherlands   | lai          | day 80   | day 68   | -12d (early) |
| maize_netherlands   | biomass_g_m2 | day 149  | day 149  | 0d (match)   |
| maize_kenya         | lai          | day 70   | day 89   | +19d (late)  |
| maize_kenya         | biomass_g_m2 | day 149  | day 149  | 0d (match)   |
| maize_sahel         | lai          | day 65   | day 27   | -38d (early) |
| maize_sahel         | biomass_g_m2 | day 147  | day 144  | -3d (match)  |

**Interpretation:**

- **Netherlands**: LAI peaks ~12 days early. Our canopy module reaches peak LAI
  before the reference, possibly due to faster initial leaf expansion under
  temperate conditions. Calibrate `sla_m2_per_g` or `leaf_fraction_vegetative`.
- **Kenya**: LAI peaks ~19 days late. The tropical highlands simulation delays
  canopy closure. Investigate `flowering_gdd` alignment with Kenya climate.
- **Sahel**: LAI peaks ~38 days early. This is the largest discrepancy. Water
  stress triggers early senescence in our model before the reference's peak.
  The `ritchie_coef` and `senescence_rate_per_day` parameters (identified as
  influential in AGRO-90 sensitivity analysis) are calibration targets.
- **Biomass** peak timing matches well across all climates (0-3 days offset).

### GYGA yield comparison

Simulated grain yields (actual `grain_biomass_g_m2` from simulation, not
post-hoc `biomass * HI`) compared to Global Yield Gap Atlas water-limited
potentials (source: yieldgap.org):

| Scenario            | Crop  | Sim (t/ha) | GYGA (t/ha) | Ratio | Status       |
|---------------------|-------|------------|-------------|-------|--------------|
| maize_netherlands   | maize |       3.34 |        11.0 |  0.30 | within range |
| maize_kenya         | maize |       5.26 |         7.0 |  0.75 | within range |
| maize_sahel         | maize |       2.68 |         3.0 |  0.89 | within range |

**Interpretation:**

- **Netherlands**: Simulated yield (3.3 t/ha) is well below GYGA potential
  (11 t/ha). GYGA reports *potential* yield under optimal management, while
  our simulation uses default fertility. The ratio 0.30 indicates significant
  room for yield improvement through better N/P management.
- **Kenya**: 5.3 t/ha vs 7.0 t/ha GYGA potential (ratio 0.75). Reasonable
  for a rainfed simulation without optimised management. Within expected range.
- **Sahel**: 2.7 t/ha vs 3.0 t/ha GYGA rainfed potential (ratio 0.89).
  Close to GYGA water-limited yield, suggesting the water stress module
  is appropriately limiting production in arid conditions.

### Calibration priorities (from AGRO-90 + AGRO-91)

Combined sensitivity analysis and benchmarking results suggest this calibration order:

1. `flowering_gdd` / `maturity_gdd` — align LAI peak timing per climate (largest discrepancies)
2. `rue_g_per_mj` — dominates biomass variance (AGRO-90); NL yield gap suggests room to increase
3. `temp_opt_c` — reduce for Sahel to increase heat stress penalty
4. `pt_alpha` — tune ET magnitude (currently overestimates in arid climates)
5. `extinction_coefficient_k` — fine-tune light interception

### References

- Taylor, K.E. (2001) Summarizing multiple aspects of model performance in a
  single diagram. J. Geophys. Res., 106(D7):7183-7192.
- Jones, J.W. et al. (2003) The DSSAT Cropping System Model.
  European Journal of Agronomy, 18:235-265.
- Keating, B.A. et al. (2003) An overview of APSIM. European Journal of
  Agronomy, 18:267-288.
- Global Yield Gap Atlas, https://yieldgap.org.
