from __future__ import annotations

from dataclasses import dataclass

from agrogame.params.phenology import PhenologyStage


@dataclass(frozen=True)
class RootParams:
    """Immutable params for root growth, depth, and nutrient-driven proliferation."""

    max_depth_cm: float = 120.0
    growth_rate_cm_per_day: float = 1.5
    distribution: str = "exponential"  # or "uniform"
    turnover_rate_per_day: float = 0.005
    # Fraction of the daily above-ground (canopy) biomass increment that is
    # allocated to root biomass. A season-averaged root:shoot partitioning
    # coefficient: cereals sit around 0.1–0.3 (DSSAT CERES root:shoot;
    # APSIM stage-dependent partitioning; WOFOST FR fraction-to-roots table,
    # Boogaard et al. 2014). Modelled here as a constant seasonal average
    # rather than a stage-declining table for simplicity.
    root_allocation_fraction: float = 0.2
    proliferation_strength: float = 0.0  # 0 disables nutrient-driven bias
    stage_multipliers: dict[PhenologyStage, float] | None = None
    # When True, allocate root fractions continuously within the boundary layer
    # instead of stepwise per full layer. This reduces discontinuities.
    continuous_distribution: bool = True
    # Scale of the kernel used for continuous distributions as a fraction of
    # current root depth (depth * kernel_scale_fraction). Used by exponential
    # and taproot kernels.
    kernel_scale_fraction: float = 0.5
