# Evaporation: Ritchie Two-Stage Model with Residue Effects

## Background

The Ritchie (1972) two-stage evaporation model partitions bare-soil
evaporation into an energy-limited phase (Stage 1) and a
diffusion-limited phase (Stage 2). Surface residue or mulch cover
reduces evaporation by shielding the soil surface.

## Stage 1 (energy-limited)

Evaporation proceeds at the atmospheric demand rate until a cumulative
limit $U$ (mm) is reached:

$$E_1 = \min(E_p,\; \theta_{avail})$$

where $E_p$ is potential soil evaporation and $\theta_{avail}$ is
plant-available water in the topsoil.

## Stage 2 (diffusion-limited)

Once $\sum E > U$, the daily rate falls as:

$$E_2 = \alpha \cdot (t + 1)^{-0.5}$$

where $\alpha$ is the Ritchie coefficient (mm d^-0.5^) and $t$ is
the cumulative evaporation beyond the Stage 1 limit.

## Wetting reset

A rainfall or irrigation event exceeding a threshold (default 10 mm)
resets the cumulative evaporation counter to zero, returning the model
to Stage 1.

## Residue / mulch reduction

Following the DSSAT approach, residue cover linearly reduces the
Stage 1 limit and Stage 2 coefficient:

$$U_{adj} = U \cdot (1 - r_1 \cdot f_c)$$

$$\alpha_{adj} = \alpha \cdot (1 - r_2 \cdot f_c)$$

where $f_c \in [0, 1]$ is the residue cover fraction, and $r_1$, $r_2$
are the maximum fractional reductions (defaults 0.6 and 0.4).

## Parameters

| Parameter | Default | Unit | Description |
|-----------|---------|------|-------------|
| `stage1_limit_mm` | 6.0 | mm | Cumulative evaporation limit for Stage 1 |
| `ritchie_coef` | 3.5 | mm d^-0.5^ | Stage 2 diffusivity coefficient |
| `residue_cover_fraction` | 0.0 | - | Surface coverage (0 = bare, 1 = full) |
| `residue_stage1_reduction` | 0.6 | - | Max fractional reduction of Stage 1 limit |
| `residue_stage2_reduction` | 0.4 | - | Max fractional reduction of Stage 2 coef |
| `wetting_reset_threshold_mm` | 10.0 | mm | Rain+irrigation to reset to Stage 1 |

## Residue decay

Residue cover decays exponentially with a configurable half-life:

$$f_c(t+1) = f_c(t) \cdot \exp\!\left(-\frac{\ln 2}{t_{1/2}}\right)$$

Set `decay_half_life_days = 0` to disable decay.

## References

- Ritchie, J.T. (1972). Model for predicting evaporation from a row
  crop with incomplete cover. *Water Resources Research*, 8(5),
  1204-1213.
- Jones, J.W. et al. (2003). The DSSAT cropping system model.
  *European Journal of Agronomy*, 18(3-4), 235-265.
- Keating, B.A. et al. (2003). An overview of APSIM, a model designed
  for farming systems simulation. *European Journal of Agronomy*,
  18(3-4), 267-288.
