from __future__ import annotations

from math import exp
from typing import List, Sequence

from agrogame.events import EventBus
from agrogame.soil.models import SoilProfile
from agrogame.soil.phenology import PhenologyStage

from .events import (
    RootBiomassUpdated,
    RootDepthChanged,
    RootDistributionUpdated,
    RootTurnoverOccurred,
)
from .params import RootParams
from .types import RootFluxes, RootState


class RootModule:
    """Pure-logic root growth: depth elongation, layer-fraction allocation, turnover."""

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
        hardpan_cm: float | None,
        water_table_cm: float | None,
        depth_cm: float,
        agg_penetration: float = 1.0,
    ) -> float:
        """Compute root elongation constraint factor.

        Args:
            agg_penetration: Aggregation-based penetration factor (0.3–1.0).
                From dynamic_state.root_penetration_factor(mwd).
                Ref: Bengough et al. 2011, J Exp Bot.
        """
        f = 1.0
        if hardpan_cm is not None and depth_cm >= hardpan_cm:
            f *= 0.2
        if water_table_cm is not None and depth_cm >= water_table_cm:
            f *= 0.5
        f *= max(0.0, min(1.0, agg_penetration))
        return max(0.0, min(1.0, f))

    def _update_depth(
        self, state: RootState, stage: PhenologyStage, constraints: dict | None
    ) -> float:
        prev = state.current_depth_cm
        hardpan = (constraints or {}).get("hardpan_cm")
        water_table = (constraints or {}).get("water_table_cm")
        agg_pen = (constraints or {}).get("agg_penetration", 1.0)
        mult = self._stage_multiplier(stage)
        cf = self._constraint_factor(hardpan, water_table, prev, agg_pen)
        inc = self.params.growth_rate_cm_per_day * mult * cf
        new = min(self.params.max_depth_cm, prev + max(0.0, inc))
        if new > prev and self.event_bus:
            self.event_bus.emit(RootDepthChanged(previous_cm=prev, new_cm=new))
        state.current_depth_cm = new
        return new - prev

    @staticmethod
    def _uniform_distribution(
        profile: SoilProfile, depth_cm: float, *, continuous: bool
    ) -> List[float]:
        fracs: List[float] = []
        cum_top = 0.0
        rooted_count = 0.0
        for i, layer in enumerate(profile.layers):
            top = cum_top
            bot = cum_top + layer.depth_cm
            cum_top = bot
            if depth_cm <= top:
                fracs.append(0.0)
                continue
            if depth_cm >= bot:
                # fully rooted layer
                fracs.append(1.0)
                rooted_count += 1.0
            else:
                # boundary layer
                rooted_len = max(0.0, depth_cm - top)
                if continuous and layer.depth_cm > 0:
                    frac = max(0.0, min(1.0, rooted_len / layer.depth_cm))
                else:
                    frac = 0.0
                fracs.append(frac)
                rooted_count += frac
                # remaining deeper layers get 0
                # fill zeros for remaining quickly
                for _ in range(i + 1, len(profile.layers)):
                    fracs.append(0.0)
                break
        # Normalize equally across rooted part
        s = rooted_count or 1.0
        return [f / s for f in fracs]

    @staticmethod
    def _exponential_distribution(
        profile: SoilProfile, depth_cm: float, *, scale_cm: float, continuous: bool
    ) -> List[float]:
        # Depth-decay kernel exp(-z/scale) integrated over rooted portion of each layer
        weights: List[float] = []
        cum_top = 0.0
        for layer in profile.layers:
            top = cum_top
            bot = cum_top + layer.depth_cm
            cum_top = bot
            if depth_cm <= top:
                weights.append(0.0)
                continue
            z0 = top
            z1 = min(bot, depth_cm)
            if continuous:
                # integral exp(-z/scale) dz = -scale * e^{-z/scale}
                w = scale_cm * (
                    exp(-z0 / max(1e-6, scale_cm)) - exp(-z1 / max(1e-6, scale_cm))
                )
            else:
                # midpoint proxy within rooted portion
                mid = 0.5 * (z0 + z1)
                w = exp(-mid / max(1.0, scale_cm)) * (z1 - z0)
            weights.append(max(0.0, w))
        s = sum(weights) or 1.0
        return [w / s for w in weights]

    @staticmethod
    def _taproot_distribution(
        profile: SoilProfile, depth_cm: float, *, scale_cm: float, continuous: bool
    ) -> List[float]:
        """Increasing weight with depth to mimic taproot dominance.

        Uses an inverted exponential so that deeper layers get higher weight
        within the rooted zone.
        """
        weights: List[float] = []
        cum_top = 0.0
        for layer in profile.layers:
            top = cum_top
            bot = cum_top + layer.depth_cm
            cum_top = bot
            if depth_cm <= top:
                weights.append(0.0)
                continue
            z0 = top
            z1 = min(bot, depth_cm)
            if continuous:
                # Use mid-depth kernel biased to depth bottom without length penalty
                mid = 0.5 * (z0 + z1)
                dist_from_bottom = max(0.0, depth_cm - mid)
                w = exp(-dist_from_bottom / max(1.0, scale_cm))
            else:
                mid = 0.5 * (z0 + z1)
                dist_from_bottom = max(0.0, depth_cm - mid)
                w = exp(-dist_from_bottom / max(1.0, scale_cm)) * (z1 - z0)
            weights.append(max(0.0, w))
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
            fracs = self._uniform_distribution(
                profile,
                state.current_depth_cm,
                continuous=self.params.continuous_distribution,
            )
        elif self.params.distribution == "taproot":
            scale = max(
                1.0,
                state.current_depth_cm * max(0.05, self.params.kernel_scale_fraction),
            )
            fracs = self._taproot_distribution(
                profile,
                state.current_depth_cm,
                scale_cm=scale,
                continuous=self.params.continuous_distribution,
            )
        else:
            scale = max(
                1.0,
                state.current_depth_cm * max(0.05, self.params.kernel_scale_fraction),
            )
            fracs = self._exponential_distribution(
                profile,
                state.current_depth_cm,
                scale_cm=scale,
                continuous=self.params.continuous_distribution,
            )
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
        dead_total = prev * self.params.turnover_rate_per_day
        state.biomass_g_m2 = max(0.0, prev - dead_total)
        state.biomass_g_m2 += max(0.0, daily_root_biomass_g_m2)
        # Emit per-layer turnover for biopore creation (#215). Skip when
        # there's no live distribution yet (pre-emergence).
        if dead_total > 0.0 and state.layer_fractions and self.event_bus:
            per_layer = tuple(dead_total * f for f in state.layer_fractions)
            self.event_bus.emit(
                RootTurnoverOccurred(per_layer_dead_mass_g_m2=per_layer)
            )
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
