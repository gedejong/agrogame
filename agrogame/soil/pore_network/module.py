"""Pore network computation from texture and aggregation state.

Derives pore size distribution per soil layer using retention-curve
partition (Rawls et al. 1982/1983) and aggregation MWD adjustment
(Dexter 2004; Bronick & Lal 2005).

Note: ``effective_porosity()`` in ``dynamic_state.py`` currently
approximates macro-derived porosity with a single scalar. Once the
pore network module is integrated into the orchestrator, that
function should delegate to the pore network's detailed breakdown.
This refactor is planned for a follow-up issue.
"""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.models import (
    SoilProfile,
)
from agrogame.soil.pore_network.events import PoreNetworkComputed
from agrogame.soil.pore_network.params import PoreNetworkParams
from agrogame.soil.pore_network.state import PoreNetworkState


class PoreNetworkModule:
    """Compute pore size distribution from soil properties."""

    def __init__(
        self,
        params: PoreNetworkParams,
        state: PoreNetworkState,
        event_bus: EventBus | None = None,
    ) -> None:
        self._params = params
        self._state = state
        self._bus = event_bus

    def compute(
        self,
        profile: SoilProfile,
        agg_state: SoilAggregationState | None = None,
    ) -> None:
        """Derive pore fractions for all layers.

        Uses retention-curve partition:
        - Macroporosity = saturation - field_capacity (gravitational water)
        - Mesoporosity  = field_capacity - wilting_point (plant-available)
        - Microporosity = wilting_point - residual (tightly held)
        - Cryptoporosity = residual (total_porosity - macro - meso - micro)

        Aggregation MWD bonus shifts macroporosity up (well-aggregated)
        or leaves it at baseline (degraded). The shift is compensated
        by reducing cryptoporosity so total remains at saturation.

        Refs:
            Rawls et al. 1982, Trans. ASAE — water retention from texture.
            Rawls et al. 1983, J. Irrig. Drain. Eng. — PTF coefficients.
            Dexter 2004, Geoderma — macropore structure and aggregation.
            Bronick & Lal 2005, Geoderma — aggregation effects on porosity.
        """
        p = self._params
        for i, layer in enumerate(profile.layers):
            total_porosity = layer.saturation

            # --- Base pore fractions from retention curve ---
            # Macro: pores that drain between saturation and FC
            base_macro = max(0.0, total_porosity - layer.field_capacity)

            # Meso: pores holding plant-available water (FC to WP)
            base_meso = max(0.0, layer.field_capacity - layer.wilting_point)

            # Residual water: texture-dependent tightly bound water
            # Ref: Rawls 1982 Table 2 — residual increases with clay
            clay = layer.clay_pct if layer.clay_pct is not None else 22.0
            residual = p.residual_water_fraction + 0.001 * clay

            # Micro: WP down to residual
            base_micro = max(0.0, layer.wilting_point - residual)

            # --- Aggregation MWD adjustment ---
            # Well-aggregated soil → more inter-aggregate macropores
            mwd_bonus = 0.0
            if agg_state is not None and i < len(agg_state.macro):
                mwd = agg_state.mwd(i)
                mwd_bonus = p.mwd_macro_coeff * max(0.0, mwd - p.mwd_baseline)

            macro = max(p.min_macro_frac, min(p.max_macro_frac, base_macro + mwd_bonus))
            meso = base_meso
            micro = base_micro

            # Crypto = residual: total - (macro + meso + micro)
            crypto = max(0.0, total_porosity - macro - meso - micro)

            # Ensure sum == total_porosity: adjust crypto as absorber
            allocated = macro + meso + micro + crypto
            if abs(allocated - total_porosity) > 1e-9:
                crypto = max(0.0, total_porosity - macro - meso - micro)

            self._state.macro[i] = macro
            self._state.meso[i] = meso
            self._state.micro[i] = micro
            self._state.crypto[i] = crypto

            # Connectivity: macropore fraction relative to total porosity
            if total_porosity > 0.0:
                self._state.connectivity[i] = min(1.0, max(0.0, macro / total_porosity))
            else:
                self._state.connectivity[i] = 0.0

            self._emit(i)

    def _emit(self, layer: int) -> None:
        if self._bus is None:
            return
        self._bus.emit(
            PoreNetworkComputed(
                layer=layer,
                macro=self._state.macro[layer],
                meso=self._state.meso[layer],
                micro=self._state.micro[layer],
                crypto=self._state.crypto[layer],
                connectivity=self._state.connectivity[layer],
            )
        )
