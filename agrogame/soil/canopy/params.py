from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CanopyParams:
    extinction_coefficient_k: float  # unitless Beer-Lambert k
    radiation_use_efficiency_g_per_mj: float  # g biomass per MJ intercepted PAR
    specific_leaf_area_m2_per_g: float  # SLA
    lai_max: float
    senescence_rate_per_day: float = 0.0
    initial_lai_at_emergence: float = 0.1  # LAI bootstrap at emergence
    senescence_vegetative_fraction: float = (
        0.1  # fraction of senescence rate during veg stage
    )
    # Cardinal temperatures for RUE scaling (DSSAT/APSIM style)
    temp_base_c: float = 8.0  # below this, temp_factor = 0
    temp_opt_c: float = 30.0  # at this, temp_factor = 1
    temp_max_c: float = 42.0  # above this, temp_factor = 0
    # Water stress feedback (AGRO-82)
    vpd_rue_ref_kpa: float = 1.5  # VPD above which RUE is reduced
    vpd_rue_slope: float = 0.1  # fractional RUE reduction per kPa above ref
    wilt_stress_threshold: float = 0.3  # stress below this triggers damage
    wilt_days_for_damage: int = 5  # consecutive days below threshold
    wilt_lai_loss_fraction: float = 0.1  # fraction of LAI lost per damage event
    stress_memory_days: int = 7  # window for running-average stress
    # Biomass partitioning: fraction of daily biomass allocated to leaves
    leaf_fraction_vegetative: float = 0.7
    leaf_fraction_flowering: float = 0.4
    leaf_fraction_grain_fill: float = 0.15
    # Stage-gated senescence multipliers
    senescence_flowering_fraction: float = 0.5  # moderate senescence at flowering
    senescence_grain_fill_max: float = 2.0  # peak multiplier at end of grain fill
    grain_fill_duration_gdd: float = 900.0  # GDD span over which senescence ramps


def cardinal_temp_factor(tmean_c: float, base: float, opt: float, tmax: float) -> float:
    """Curvilinear temperature response (DSSAT/APSIM style).

    Below optimum: concave (sqrt) curve — rises quickly from base,
    matching the beta-function shape used in DSSAT CERES models.
    Above optimum: linear decline — crops are more sensitive to
    supra-optimal heat.

    Returns 0 at base and max, 1 at optimum.
    """
    if tmean_c <= base or tmean_c >= tmax:
        return 0.0
    if tmean_c <= opt:
        x = (tmean_c - base) / (opt - base)
        return float(x**0.5)
    return (tmax - tmean_c) / (tmax - opt)
