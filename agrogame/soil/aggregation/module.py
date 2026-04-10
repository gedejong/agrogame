"""Aggregate formation and breakdown logic."""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.aggregation.params import SoilAggregationParams
from agrogame.soil.aggregation.events import (
    AggregateStructureUpdated,
    TillageApplied,
    StructureDegraded,
)


class AggregationModule:
    """Computes aggregate formation and breakdown per soil layer.

    Formation: biological (root/fungal binding) promotes micro/meso → macro.
    Breakdown: tillage, wet-dry, freeze-thaw, raindrop impact degrade macro.

    Ref: Six et al. 2004, Soil Tillage Res;
         Tisdall & Oades 1982, J Soil Sci.
    """

    def __init__(
        self,
        params: SoilAggregationParams,
        state: SoilAggregationState,
        event_bus: EventBus | None = None,
    ) -> None:
        self.params = params
        self.state = state
        self.event_bus = event_bus

    def weekly_step(
        self,
        root_density_fractions: list[float],
        fungal_fractions: list[float],
        temperature_c: float,
    ) -> None:
        """Advance aggregate formation by one week.

        Args:
            root_density_fractions: Per-layer root density (0–1).
            fungal_fractions: Per-layer fungal fraction of microbial biomass (0–1).
            temperature_c: Mean weekly temperature (°C).
        """
        p = self.params
        n = len(self.state.micro)
        temp_factor = self._temp_factor(temperature_c)

        for i in range(n):
            rf = root_density_fractions[i] if i < len(root_density_fractions) else 0.0
            ff = fungal_fractions[i] if i < len(fungal_fractions) else 0.0

            # Biological activity index (0–1): weighted combination of
            # root density and fungal fraction.
            # Ref: Tisdall & Oades 1982 — roots and fungi are primary binding agents
            bio_activity = p.root_formation_weight * min(
                rf, 1.0
            ) + p.fungal_formation_weight * min(ff, 1.0)
            bio_activity = min(bio_activity, 1.0)

            # Micro → meso formation: baseline from abiotic clay flocculation
            # (rate > 0 even without roots/fungi), boosted up to 2x by biology.
            # Ref: Tisdall & Oades 1982 — transient vs persistent binding agents.
            meso_gain = (
                p.meso_formation_rate_per_week * temp_factor * (1.0 + bio_activity)
            )
            meso_gain = min(meso_gain, self.state.micro[i] * 0.5)  # cap at 50% of micro

            # Meso → macro formation (biological aggregation)
            macro_gain = p.macro_formation_rate_per_week * bio_activity * temp_factor
            macro_gain = min(macro_gain, self.state.meso[i] * 0.5)  # cap at 50% of meso

            self.state.micro[i] -= meso_gain
            self.state.meso[i] += meso_gain - macro_gain
            self.state.macro[i] += macro_gain

            self.state.normalize(i)
            self._emit_update(i)

    def apply_tillage(
        self,
        intensity: float,
        layer_depths_cm: list[float] | None = None,
    ) -> None:
        """Apply tillage disturbance to plow-depth layers only.

        Destroys macroaggregates proportional to intensity (0–1).
        Destroyed macro redistributes to meso (70%) and micro (30%).
        Only affects layers within plow depth (scales with intensity).

        Ref: Six et al. 2000, SSSAJ — tillage destroys 30–70% of macroaggregates.

        Args:
            intensity: Tillage intensity (0.0 = no-till, 1.0 = moldboard plow).
            layer_depths_cm: Per-layer thickness. If None, all layers affected.
        """
        import math

        if math.isnan(intensity):
            return
        intensity = max(0.0, min(1.0, intensity))
        if intensity <= 0.0:
            return

        p = self.params
        # Destruction fraction scales linearly between min and max
        destruction_frac = (
            p.tillage_macro_destruction_min
            + (p.tillage_macro_destruction_max - p.tillage_macro_destruction_min)
            * intensity
        )

        # Plow depth scales with intensity (light tillage = shallower)
        plow_depth = p.plow_depth_cm * intensity
        n = len(self.state.micro)
        cumulative_depth = 0.0
        for i in range(n):
            # Only affect layers within plow depth
            if layer_depths_cm is not None and i < len(layer_depths_cm):
                cumulative_depth += layer_depths_cm[i]
                if cumulative_depth - layer_depths_cm[i] >= plow_depth:
                    break
            macro_lost = self.state.macro[i] * destruction_frac
            # Redistribute: 70% → meso, 30% → micro
            # Ref: Six et al. 2004 — breakdown products are mostly meso-sized
            self.state.macro[i] -= macro_lost
            self.state.meso[i] += macro_lost * 0.7
            self.state.micro[i] += macro_lost * 0.3
            self.state.normalize(i)
            self._emit_update(i)

        if self.event_bus:
            self.event_bus.emit(
                TillageApplied(
                    intensity=intensity,
                    macro_destroyed_frac=destruction_frac,
                )
            )

    def apply_wet_dry_breakdown(self, layer: int) -> None:
        """Apply wet-dry cycle aggregate breakdown for one layer.

        Ref: Denef et al. 2001, Soil Biol Biochem — 5–15% macro loss per cycle.
        """
        if layer >= len(self.state.micro):
            return
        macro_lost = self.state.macro[layer] * self.params.wet_dry_macro_breakdown
        self.state.macro[layer] -= macro_lost
        self.state.meso[layer] += macro_lost * 0.6
        self.state.micro[layer] += macro_lost * 0.4
        self.state.normalize(layer)
        if self.event_bus:
            self.event_bus.emit(
                StructureDegraded(
                    layer=layer,
                    cause="wet_dry",
                    macro_lost_frac=self.params.wet_dry_macro_breakdown,
                )
            )

    def apply_freeze_thaw_breakdown(self, layer: int) -> None:
        """Apply freeze-thaw cycle aggregate breakdown for one layer.

        Ref: Six et al. 2004 — 10–20% macro loss per cycle.
        """
        if layer >= len(self.state.micro):
            return
        macro_lost = self.state.macro[layer] * self.params.freeze_thaw_macro_breakdown
        self.state.macro[layer] -= macro_lost
        self.state.meso[layer] += macro_lost * 0.5
        self.state.micro[layer] += macro_lost * 0.5
        self.state.normalize(layer)
        if self.event_bus:
            self.event_bus.emit(
                StructureDegraded(
                    layer=layer,
                    cause="freeze_thaw",
                    macro_lost_frac=self.params.freeze_thaw_macro_breakdown,
                )
            )

    def apply_raindrop_impact(self, rainfall_mm: float) -> None:
        """Apply raindrop impact to surface layer (layer 0 only).

        Ref: Le Bissonnais 1996, Catena — surface crusting and aggregate
        destruction from raindrop kinetic energy.
        """
        p = self.params
        if rainfall_mm <= p.rain_threshold_mm:
            return
        if not self.state.micro:
            return
        excess_mm = rainfall_mm - p.rain_threshold_mm
        breakdown = min(p.raindrop_surface_breakdown * excess_mm, 0.3)
        macro_lost = self.state.macro[0] * breakdown
        self.state.macro[0] -= macro_lost
        self.state.meso[0] += macro_lost * 0.5
        self.state.micro[0] += macro_lost * 0.5
        self.state.normalize(0)
        if self.event_bus and macro_lost > 1e-6:
            self.event_bus.emit(
                StructureDegraded(
                    layer=0,
                    cause="raindrop",
                    macro_lost_frac=breakdown,
                )
            )

    def _temp_factor(self, temperature_c: float) -> float:
        """Cardinal temperature function for biological formation.

        Bell-shaped: 0 at Tmin and Tmax, 1.0 at Topt.
        Ref: Yan & Hunt 1999, Annals of Botany — beta function model;
             used in APSIM/DSSAT for biological rate scaling.
        """
        p = self.params
        if temperature_c <= p.temp_min_c or temperature_c >= p.temp_max_c:
            return 0.0
        # Normalized position: 0 at Tmin, 1 at Topt
        num = temperature_c - p.temp_min_c
        denom = p.temp_optimum_c - p.temp_min_c
        if denom <= 0.0:
            return 0.0
        ratio = num / denom
        # Declining above optimum: linear ramp to 0 at Tmax
        if temperature_c > p.temp_optimum_c:
            above = (p.temp_max_c - temperature_c) / (p.temp_max_c - p.temp_optimum_c)
            return max(0.0, above)
        # Below optimum: concave ramp (square root shape for smooth onset)
        return min(1.0, ratio)

    def _emit_update(self, layer: int) -> None:
        if self.event_bus:
            self.event_bus.emit(
                AggregateStructureUpdated(
                    layer=layer,
                    micro=self.state.micro[layer],
                    meso=self.state.meso[layer],
                    macro=self.state.macro[layer],
                    mwd_mm=self.state.mwd(layer),
                )
            )
