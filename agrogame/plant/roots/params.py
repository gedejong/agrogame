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
    # Below-ground share of the single finite daily assimilate pool (#337).
    # Competitive partition coefficient (Σ shoot+root = 1): assimilate routed
    # here is withheld from shoot/grain, so raising it lowers shoot/grain and
    # never inflates total NPP. The *standing* root:shoot ratio that emerges
    # differs from this input fraction (turnover trims roots; shoot carries
    # more standing mass), so it is not tautological. Season-averaged constant
    # rather than a stage-declining table for simplicity; cereals partition
    # ~0.1–0.3 to roots (DSSAT CERES root:shoot; APSIM stage-dependent
    # partitioning; WOFOST FR fraction-to-roots table, Boogaard et al. 2014).
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
