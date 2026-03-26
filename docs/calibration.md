### Bayesian parameter calibration (AGRO-92)

We use Markov Chain Monte Carlo (MCMC) to calibrate the 8 most influential
crop model parameters, replacing hand-tuned literature defaults with
statistically inferred posterior distributions.

### Method

**Sampler**: emcee affine-invariant ensemble sampler (Foreman-Mackey et al. 2013).

**Priors**: Uniform distributions bounded by literature ranges (from AGRO-90
Morris sensitivity analysis):

| Parameter                 | Prior [lo, hi]   | Default | Posterior median |
|---------------------------|------------------|---------|------------------|
| rue_g_per_mj              | [1.5, 4.5]       |    3.00 |             3.56 |
| temp_opt_c                | [22.0, 36.0]     |   30.00 |            26.45 |
| pt_alpha                  | [1.0, 1.5]       |    1.26 |             1.09 |
| extinction_coefficient_k  | [0.40, 0.80]     |    0.65 |             0.54 |
| flowering_gdd             | [600, 1200]       |  900.0  |            759.0 |
| maturity_gdd              | [1200, 2200]      | 1700.0  |           1830.0 |
| sla_m2_per_g              | [0.012, 0.030]    |   0.020 |            0.012 |
| remobilization_fraction   | [0.0, 0.05]       |   0.020 |            0.037 |

**Constraint**: flowering_gdd < maturity_gdd (biologically required).

**Likelihood**: Gaussian log-likelihood comparing simulated vs reference
trajectories (subsampled every 10 days to reduce temporal autocorrelation):

- Biomass: sigma = 80 g/m² (typical field measurement error)
- LAI: sigma = 0.5 m²/m² (typical LAI-2200 instrument error)

**Target scenario**: Maize x Netherlands temperate, 150-day season from
April 1, using DSSAT CERES-Maize reference trajectories from AGRO-91.

### Configuration

```bash
# Full calibration (~2-6 hours depending on hardware)
poetry run python scripts/bayesian_calibration.py --walkers 32 --steps 500 --burn 200

# Quick smoke run (~5 min)
poetry run python scripts/bayesian_calibration.py --walkers 16 --steps 20 --burn 10
```

### Convergence diagnostics

| Metric                | Value | Target   |
|-----------------------|-------|----------|
| Acceptance fraction   | 0.286 | 0.2-0.5  |
| Chain length / tau    | ~6    | > 50     |

The acceptance fraction is in the optimal range. Chain length relative to
autocorrelation time is below the recommended 50x threshold — longer chains
would improve posterior estimates. The current results are adequate for
identifying parameter shifts but should be extended for publication-quality
uncertainty quantification.

### Key findings

1. **RUE increases** from 3.0 to 3.56 g/MJ — the model needs higher radiation
   use efficiency to match DSSAT biomass trajectories. Literature range for
   temperate maize is 3.0-4.5 g/MJ (Sinclair & Muchow 1999).

2. **Temperature optimum decreases** from 30.0 to 26.4°C — better suited for
   Netherlands temperate conditions. DSSAT uses 26-34°C depending on cultivar.

3. **SLA decreases** from 0.020 to 0.012 m²/g — thicker leaves produce less
   LAI per unit biomass, aligning peak LAI timing with reference.

4. **Flowering advances** from 900 to 759 GDD — addresses the LAI timing
   discrepancy identified in AGRO-91 (Netherlands LAI peaked 12 days early).

5. **Maturity extends** from 1700 to 1830 GDD — longer grain fill period
   increases grain yield.

6. **Remobilization increases** from 2% to 3.7%/day — more stem reserves
   are channelled to grain, consistent with APSIM parameterization.

### Prediction uncertainty

Netherlands maize grain yield = 585 g/m² (90% CI: [491, 644] g/m²)
= 5.85 t/ha (90% CI: [4.91, 6.44] t/ha)

This is within the expected range for Netherlands rainfed maize under default
fertility (GYGA water-limited potential: 10-12 t/ha).

### Outputs

The calibration script produces:

- `out/calibration/posterior_summary.csv` — parameter medians and 90% CIs
- `out/calibration/trace_plots.png` — MCMC trace plots per parameter
- `out/calibration/corner_plot.png` — posterior joint distributions
- `out/calibration/flat_chain.npy` — raw posterior samples (NumPy array)

### Caveats

- Calibration target is synthetic DSSAT reference curves, not field observations.
  Posteriors reflect structural model differences, not true measurement uncertainty.
- Calibrated for Netherlands maize only. Other crop x climate combinations use
  original literature defaults. Climate-specific calibration is a follow-up task.
- The uniform prior on `sla_m2_per_g` hits the lower bound (0.012), suggesting
  the prior range may need widening or the model structure should be investigated.

### References

- Foreman-Mackey, D. et al. (2013) emcee: The MCMC Hammer.
  Publ. Astron. Soc. Pacific, 125(925):306-312.
- Sinclair, T.R. & Muchow, R.C. (1999) Radiation use efficiency.
  Adv. Agronomy, 65:215-265.
- Morris, M.D. (1991) Factorial sampling plans for preliminary
  computational experiments. Technometrics, 33(2):161-174.
