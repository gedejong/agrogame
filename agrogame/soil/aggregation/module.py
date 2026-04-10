"""Aggregate formation and breakdown logic."""

from __future__ import annotations

from typing import Optional

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
        event_bus: Optional[EventBus] = None,
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

            # Micro → meso formation (clay flocculation + organic binding)
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

    def apply_tillage(self, intensity: float) -> None:
        """Apply tillage disturbance to all layers.

        Destroys macroaggregates proportional to intensity (0–1).
        Destroyed macro redistributes to meso (70%) and micro (30%).

        Ref: Six et al. 2000, SSSAJ — tillage destroys 30–70% of macroaggregates.

        Args:
            intensity: Tillage intensity (0.0 = no-till, 1.0 = moldboard plow).
        """
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

        n = len(self.state.micro)
        for i in range(n):
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
        """Temperature scaling for biological formation.

        Q10 function centered on optimum temperature.
        Returns 0–1 multiplier; peaks at 1.0 at optimum.
        """
        p = self.params
        if temperature_c <= 0.0:
            return 0.0
        diff = temperature_c - p.temp_formation_optimum_c
        factor = p.temp_formation_q10 ** (diff / 10.0)
        # Cap at 1.0 (optimum) and scale down for cold
        return float(min(1.0, factor))

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
