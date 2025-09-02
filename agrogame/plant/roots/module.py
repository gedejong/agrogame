from __future__ import annotations

from math import exp
from typing import List, Sequence

from agrogame.events import EventBus
from agrogame.soil.models import SoilProfile
from agrogame.soil.phenology import PhenologyStage

from .events import RootBiomassUpdated, RootDepthChanged, RootDistributionUpdated
from .params import RootParams
from .types import RootFluxes, RootState


class RootModule:
    def __init__(self, params: RootParams, event_bus: EventBus | None = None) -> None:
        self.params = params
        self.event_bus = event_bus

    def _stage_multiplier(self, stage: PhenologyStage) -> float:
        if self.params.stage_multipliers and stage in self.params.stage_multipliers:
            return max(0.0, self.params.stage_multipliers[stage])
        # default: vegetative emphasis
        if stage in (PhenologyStage.EMERGED, PhenologyStage.VEGETATIVE):
            return 1.0
        if stage is PhenologyStage.FLOWERING:
            return 0.6
        return 0.3

    @staticmethod
    def _constraint_factor(
        hardpan_cm: float | None, water_table_cm: float | None, depth_cm: float
    ) -> float:
        f = 1.0
        if hardpan_cm is not None and depth_cm >= hardpan_cm:
            f *= 0.2
        if water_table_cm is not None and depth_cm >= water_table_cm:
            f *= 0.5
        return max(0.0, min(1.0, f))

    def _update_depth(
        self, state: RootState, stage: PhenologyStage, constraints: dict | None
    ) -> float:
        prev = state.current_depth_cm
        hardpan = (constraints or {}).get("hardpan_cm")
        water_table = (constraints or {}).get("water_table_cm")
        mult = self._stage_multiplier(stage)
        cf = self._constraint_factor(hardpan, water_table, prev)
        inc = self.params.growth_rate_cm_per_day * mult * cf
        new = min(self.params.max_depth_cm, prev + max(0.0, inc))
        if new > prev and self.event_bus:
            self.event_bus.emit(RootDepthChanged(previous_cm=prev, new_cm=new))
        state.current_depth_cm = new
        return new - prev

    @staticmethod
    def _uniform_distribution(profile: SoilProfile, depth_cm: float) -> List[float]:
        fracs: List[float] = []
        cum = 0.0
        rooted_layers: List[int] = []
        for i, layer in enumerate(profile.layers):
            cum += layer.depth_cm
            if cum <= depth_cm:
                rooted_layers.append(i)
                fracs.append(0.0)  # placeholder
            else:
                fracs.append(0.0)
        n = len(rooted_layers) or 1
        for i in rooted_layers:
            fracs[i] = 1.0 / n
        return fracs

    @staticmethod
    def _exponential_distribution(profile: SoilProfile, depth_cm: float) -> List[float]:
        # Simple decaying weight with depth; more mass near surface
        weights: List[float] = []
        cum_top = 0.0
        for layer in profile.layers:
            cum_top_next = cum_top + layer.depth_cm
            if cum_top_next <= depth_cm:
                # use layer midpoint depth as proxy
                mid = cum_top + 0.5 * layer.depth_cm
                w = exp(-mid / max(1.0, depth_cm * 0.5))
                weights.append(w)
            else:
                weights.append(0.0)
            cum_top = cum_top_next
        s = sum(weights) or 1.0
        return [w / s for w in weights]

    @staticmethod
    def _taproot_distribution(profile: SoilProfile, depth_cm: float) -> List[float]:
        """Increasing weight with depth to mimic taproot dominance.

        Uses an inverted exponential so that deeper layers get higher weight
        within the rooted zone.
        """
        weights: List[float] = []
        cum_top = 0.0
        for layer in profile.layers:
            cum_top_next = cum_top + layer.depth_cm
            if cum_top_next <= depth_cm:
                # distance from bottom of rooted zone
                mid = cum_top + 0.5 * layer.depth_cm
                dist_from_bottom = max(0.0, depth_cm - mid)
                # invert: larger weight when dist_from_bottom small (i.e., near bottom)
                w = exp(-dist_from_bottom / max(1.0, depth_cm * 0.5))
                weights.append(w)
            else:
                weights.append(0.0)
            cum_top = cum_top_next
        s = sum(weights) or 1.0
        return [w / s for w in weights]

    @staticmethod
    def _apply_proliferation(
        fracs: List[float], nutrient_signal: Sequence[float] | None, strength: float
    ) -> List[float]:
        if not nutrient_signal or strength <= 0.0:
            return fracs
        biased = [
            max(0.0, f + strength * max(0.0, n))
            for f, n in zip(fracs, nutrient_signal, strict=False)
        ]
        s = sum(biased) or 1.0
        return [b / s for b in biased]

    def _update_distribution(
        self,
        state: RootState,
        profile: SoilProfile | None,
        nutrient_signal: Sequence[float] | None,
    ) -> None:
        # If no profile is provided (e.g., lightweight orchestrator demo), skip
        if profile is None:
            return
        if self.params.distribution == "uniform":
            fracs = self._uniform_distribution(profile, state.current_depth_cm)
        elif self.params.distribution == "taproot":
            fracs = self._taproot_distribution(profile, state.current_depth_cm)
        else:
            fracs = self._exponential_distribution(profile, state.current_depth_cm)
        fracs = self._apply_proliferation(
            fracs, nutrient_signal, self.params.proliferation_strength
        )
        state.layer_fractions = fracs
        if self.event_bus:
            self.event_bus.emit(RootDistributionUpdated(fractions=tuple(fracs)))

    def _update_biomass(
        self, state: RootState, daily_root_biomass_g_m2: float
    ) -> float:
        prev = state.biomass_g_m2
        # turnover first
        state.biomass_g_m2 = max(
            0.0, state.biomass_g_m2 * (1.0 - self.params.turnover_rate_per_day)
        )
        state.biomass_g_m2 += max(0.0, daily_root_biomass_g_m2)
        if state.biomass_g_m2 != prev and self.event_bus:
            self.event_bus.emit(RootBiomassUpdated(biomass_g_m2=state.biomass_g_m2))
        return state.biomass_g_m2 - prev

    def daily_step(
        self,
        state: RootState,
        profile: SoilProfile,
        stage: PhenologyStage,
        daily_root_biomass_g_m2: float = 0.0,
        nutrient_signal: Sequence[float] | None = None,
        constraints: dict | None = None,
    ) -> RootFluxes:
        d_depth = self._update_depth(state, stage, constraints)
        _ = self._update_biomass(state, daily_root_biomass_g_m2)
        self._update_distribution(state, profile, nutrient_signal)
        return RootFluxes(depth_inc_cm=d_depth, biomass_delta_g_m2=0.0)

    @staticmethod
    def root_shoot_ratio(root_biomass_g_m2: float, shoot_biomass_g_m2: float) -> float:
        if shoot_biomass_g_m2 <= 0.0:
            return float("inf") if root_biomass_g_m2 > 0.0 else 0.0
        return max(0.0, root_biomass_g_m2) / max(1e-9, shoot_biomass_g_m2)
