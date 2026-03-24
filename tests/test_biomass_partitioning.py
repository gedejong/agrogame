from __future__ import annotations

from agrogame.soil.phenology import PhenologyStage
from agrogame.plant.biomass import (
    BiomassPartitioner,
    PartitioningParams,
)


def _params() -> PartitioningParams:
    return PartitioningParams(
        partitioning={
            PhenologyStage.EMERGED: {
                "leaf": 0.5,
                "stem": 0.2,
                "root": 0.3,
                "grain": 0.0,
            },
            PhenologyStage.VEGETATIVE: {
                "leaf": 0.45,
                "stem": 0.35,
                "root": 0.2,
                "grain": 0.0,
            },
            PhenologyStage.FLOWERING: {
                "leaf": 0.25,
                "stem": 0.25,
                "root": 0.1,
                "grain": 0.4,
            },
            PhenologyStage.GRAIN_FILL: {
                "leaf": 0.1,
                "stem": 0.1,
                "root": 0.05,
                "grain": 0.75,
            },
        },
        harvest_index_potential=0.5,
        remobilization_efficiency=0.5,
    )


def test_partitioning_sums_and_pools_update() -> None:
    part = BiomassPartitioner(_params())
    alloc = part.partition_daily(PhenologyStage.VEGETATIVE, daily_biomass_g_m2=100.0)
    total = alloc.leaf_g_m2 + alloc.stem_g_m2 + alloc.root_g_m2 + alloc.grain_g_m2
    assert abs(total - 100.0) < 1e-6
    assert (
        part.pools.leaf_g_m2 > 0
        and part.pools.stem_g_m2 > 0
        and part.pools.root_g_m2 > 0
    )


def test_remobilization_in_grain_fill_increases_grain_and_reduces_sources() -> None:
    part = BiomassPartitioner(_params())
    # Build some leaf/stem biomass first
    for _ in range(5):
        part.partition_daily(PhenologyStage.VEGETATIVE, 50.0)
    leaf_before = part.pools.leaf_g_m2
    stem_before = part.pools.stem_g_m2
    grain_before = part.pools.grain_g_m2
    part.partition_daily(PhenologyStage.GRAIN_FILL, 50.0)
    assert part.pools.leaf_g_m2 < leaf_before
    assert part.pools.stem_g_m2 < stem_before
    assert part.pools.grain_g_m2 > grain_before


def test_harvest_index_reasonable_range() -> None:
    part = BiomassPartitioner(_params())
    for _ in range(10):
        part.partition_daily(PhenologyStage.VEGETATIVE, 80.0)
    for _ in range(10):
        part.partition_daily(PhenologyStage.GRAIN_FILL, 80.0)
    hi = part.harvest_index()
    assert 0.1 <= hi <= 0.9
