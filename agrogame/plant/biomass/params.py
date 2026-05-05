from __future__ import annotations

from dataclasses import dataclass

from agrogame.params.phenology import PhenologyStage


@dataclass(frozen=True)
class PartitioningParams:
    """Frozen biomass-partitioning per phenology stage, with stress responses."""

    partitioning: dict[PhenologyStage, dict[str, float]]
    harvest_index_potential: float = 0.5
    remobilization_efficiency: float = 0.5
    # Stress-response tuning
    drought_root_bias: float = 0.2  # max fraction shifted to roots at full drought
