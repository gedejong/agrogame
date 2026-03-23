"""Tests covering missing lines in agrogame/plant/biomass/module.py."""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.plant.biomass import BiomassPartitioner, PartitioningParams
from agrogame.plant.biomass.events import BiomassPartitioned
from agrogame.plant.stress import StressFactors
from agrogame.soil.phenology import PhenologyStage


def _params() -> PartitioningParams:
    return PartitioningParams(
        partitioning={
            PhenologyStage.VEGETATIVE: {
                "leaf": 0.45,
                "stem": 0.35,
                "root": 0.2,
                "grain": 0.0,
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


# ---------------------------------------------------------------------------
# Fallback partition fractions (line 33)
# ---------------------------------------------------------------------------


def test_fallback_partition_fractions() -> None:
    """Cover line 33: stage not in partitioning dict uses fallback."""
    part = BiomassPartitioner(_params())
    alloc = part.partition_daily(PhenologyStage.MATURITY, daily_biomass_g_m2=100.0)
    total = alloc.leaf_g_m2 + alloc.stem_g_m2 + alloc.root_g_m2 + alloc.grain_g_m2
    assert abs(total - 100.0) < 1e-6


# ---------------------------------------------------------------------------
# Stress-driven root bias (lines 56-68)
# ---------------------------------------------------------------------------


def test_drought_stress_shifts_to_roots() -> None:
    """Cover lines 56-68: _apply_stress with water deficit."""
    part = BiomassPartitioner(
        PartitioningParams(
            partitioning={
                PhenologyStage.VEGETATIVE: {
                    "leaf": 0.4,
                    "stem": 0.4,
                    "root": 0.2,
                    "grain": 0.0,
                },
            },
            drought_root_bias=0.3,
        )
    )
    stress = StressFactors(water=0.3, nitrogen=1.0)
    alloc = part.partition_daily(
        PhenologyStage.VEGETATIVE, daily_biomass_g_m2=100.0, stress=stress
    )
    # Root allocation should be higher than the default 0.2 * 100 = 20
    assert alloc.root_g_m2 > 20.0


# ---------------------------------------------------------------------------
# Sink limitation (line 94)
# ---------------------------------------------------------------------------


def test_sink_limitation_caps_grain() -> None:
    """Cover line 94: grain_alloc capped by potential HI."""
    part = BiomassPartitioner(
        PartitioningParams(
            partitioning={
                PhenologyStage.GRAIN_FILL: {
                    "leaf": 0.0,
                    "stem": 0.0,
                    "root": 0.0,
                    "grain": 1.0,
                },
            },
            harvest_index_potential=0.01,  # very low
            remobilization_efficiency=0.0,
        )
    )
    # Build some biomass first so potential_grain is nonzero
    part.pools.leaf_g_m2 = 100.0
    part.pools.stem_g_m2 = 100.0
    alloc = part.partition_daily(PhenologyStage.GRAIN_FILL, daily_biomass_g_m2=500.0)
    # Grain should be capped well below 500
    assert alloc.grain_g_m2 < 500.0


# ---------------------------------------------------------------------------
# Event emission (line 112)
# ---------------------------------------------------------------------------


def test_event_emission() -> None:
    """Cover line 112: BiomassPartitioned event emitted."""
    bus = EventBus()
    captured = []
    bus.subscribe(BiomassPartitioned, lambda e: captured.append(e))
    part = BiomassPartitioner(_params(), event_bus=bus)
    part.partition_daily(PhenologyStage.VEGETATIVE, daily_biomass_g_m2=50.0)
    assert len(captured) == 1
