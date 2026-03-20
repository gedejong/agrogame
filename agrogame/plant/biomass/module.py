from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.phenology import PhenologyStage

from .params import PartitioningParams
from .types import BiomassPools, BiomassAllocations
from agrogame.plant.stress import StressFactors
from .events import BiomassPartitioned


class BiomassPartitioner:
    """Stage-based biomass partitioning with simple remobilization support."""

    def __init__(self, params: PartitioningParams, event_bus: EventBus | None = None):
        self.params = params
        self.event_bus = event_bus
        self.pools = BiomassPools()

    def harvest_index(self) -> float:
        total = (
            self.pools.leaf_g_m2
            + self.pools.stem_g_m2
            + self.pools.root_g_m2
            + self.pools.grain_g_m2
        )
        return 0.0 if total <= 0 else self.pools.grain_g_m2 / total

    def _partition_fractions(self, stage: PhenologyStage) -> dict[str, float]:
        mapping = self.params.partitioning.get(stage)
        if not mapping:
            # fallback: vegetative-like
            mapping = {"leaf": 0.4, "stem": 0.4, "root": 0.2, "grain": 0.0}
        s = sum(mapping.values()) or 1.0
        return {k: max(0.0, v) / s for k, v in mapping.items()}

    def _remobilize_if_needed(self, stage: PhenologyStage) -> float:
        if stage != PhenologyStage.GRAIN_FILL:
            return 0.0
        moved = (
            0.2 * self.params.remobilization_efficiency * self.pools.stem_g_m2
            + 0.3 * self.params.remobilization_efficiency * self.pools.leaf_g_m2
        )
        self.pools.stem_g_m2 -= (
            0.2 * self.params.remobilization_efficiency * self.pools.stem_g_m2
        )
        self.pools.leaf_g_m2 -= (
            0.3 * self.params.remobilization_efficiency * self.pools.leaf_g_m2
        )
        return moved

    def _apply_stress(
        self, fractions: dict[str, float], stress: StressFactors
    ) -> dict[str, float]:
        # Drought shifts some allocation from shoots/grain to roots
        water_deficit = max(0.0, 1.0 - stress.water)
        shift = self.params.drought_root_bias * water_deficit
        # take proportionally from leaf/stem/grain
        take_keys = [k for k in ("leaf", "stem", "grain") if k in fractions]
        taken_total = 0.0
        for k in take_keys:
            take = fractions[k] * shift
            fractions[k] = max(0.0, fractions[k] - take)
            taken_total += take
        fractions["root"] = fractions.get("root", 0.0) + taken_total
        # Re-normalize
        s = sum(fractions.values()) or 1.0
        return {k: v / s for k, v in fractions.items()}

    def _apply_sink_limitation(
        self, stage: PhenologyStage, grain_alloc: float
    ) -> float:
        if stage != PhenologyStage.GRAIN_FILL:
            return grain_alloc
        # Simple cap: cannot exceed potential HI scaled pool
        total = (
            self.pools.leaf_g_m2
            + self.pools.stem_g_m2
            + self.pools.root_g_m2
            + self.pools.grain_g_m2
        )
        potential_grain = self.params.harvest_index_potential * max(0.0, total)
        deficit = max(0.0, potential_grain - self.pools.grain_g_m2)
        return min(grain_alloc, deficit)

    def partition_daily(
        self,
        stage: PhenologyStage,
        daily_biomass_g_m2: float,
        stress: StressFactors | None = None,
    ) -> BiomassAllocations:
        fractions = self._partition_fractions(stage)
        if stress is not None:
            fractions = self._apply_stress(fractions, stress)
        increment = max(0.0, daily_biomass_g_m2) + self._remobilize_if_needed(stage)

        grain = increment * fractions.get("grain", 0.0)
        grain = self._apply_sink_limitation(stage, grain)
        alloc = BiomassAllocations(
            leaf_g_m2=increment * fractions.get("leaf", 0.0),
            stem_g_m2=increment * fractions.get("stem", 0.0),
            root_g_m2=increment * fractions.get("root", 0.0),
            grain_g_m2=grain,
        )

        self.pools.leaf_g_m2 += alloc.leaf_g_m2
        self.pools.stem_g_m2 += alloc.stem_g_m2
        self.pools.root_g_m2 += alloc.root_g_m2
        self.pools.grain_g_m2 += alloc.grain_g_m2

        if self.event_bus:
            self.event_bus.emit(
                BiomassPartitioned(allocations=alloc, pools_after=self.pools)
            )
        return alloc
