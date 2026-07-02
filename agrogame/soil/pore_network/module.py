"""Pore network computation from texture and aggregation state.

Derives pore size distribution per soil layer using retention-curve
partition (Rawls et al. 1982/1983) and aggregation MWD adjustment
(Dexter 2004; Bronick & Lal 2005).

Note: ``effective_porosity()`` in ``dynamic_state.py`` currently
approximates macro-derived porosity with a single scalar. Once the
pore network module is integrated into the orchestrator (planned
follow-up), that function should delegate to the pore network's
detailed breakdown. Orchestrator wiring and ``SoilSnapshot``
persistence are also deferred to that follow-up.
"""

from __future__ import annotations

from agrogame.events import EventBus
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.params.ports import SoilProfileView
from agrogame.soil.models import TEXTURE_TO_SAND
from agrogame.soil.pore_network.events import PoreNetworkComputed
from agrogame.soil.pore_network.params import PoreNetworkParams
from agrogame.soil.pore_network.state import PoreNetworkState

# Fallback sand fraction (%) for textures absent from TEXTURE_TO_SAND;
# medium loam is the neutral default (matches clay_pct fallback of 22%).
_DEFAULT_SAND_PCT = 42.0


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

    @property
    def state(self) -> PoreNetworkState:
        return self._state

    def set_state(self, state: PoreNetworkState) -> None:
        """Replace state contents in place to preserve aliases.

        Runtimes and the orchestrator hold references to the underlying
        ``PoreNetworkState``. Mutating in place keeps those references
        valid after a snapshot restore.
        """
        self._state.macro = list(state.macro)
        self._state.meso = list(state.meso)
        self._state.micro = list(state.micro)
        self._state.crypto = list(state.crypto)
        self._state.connectivity = list(state.connectivity)

    def compute(
        self,
        profile: SoilProfileView,
        agg_state: SoilAggregationState | None = None,
    ) -> None:
        """Derive pore fractions for all layers.

        Uses retention-curve partition:
        - Drainable pool = saturation - field_capacity (empties by gravity
          above FC, i.e. pores >~9 um). This is split into true
          macroporosity (>50 um) and coarse transmission mesoporosity
          (10-50 um). The macropore share rises with sand content
          (``macro_split_base`` + ``macro_split_sand_slope`` * sand%),
          so a default loam lands at ~5-15% macroporosity (#340) rather
          than equating the whole drainable pool with macropores.
        - Mesoporosity  = (field_capacity - wilting_point) plant-available
          water storage PLUS the coarse (non-macro) part of the drainable
          pool.
        - Microporosity = wilting_point - residual (tightly held).
        - Cryptoporosity = residual (total_porosity - macro - meso - micro).

        Aggregation MWD bonus shifts macroporosity up (well-aggregated)
        or leaves it at baseline (degraded); the coarse-mesopore share
        shrinks correspondingly so the drainable pool is conserved. Macro
        is capped at the drainable pool so it can never exceed it.

        Refs:
            Rawls et al. 1982, Trans. ASAE — water retention from texture.
            Rawls et al. 1983, J. Irrig. Drain. Eng. — PTF coefficients.
            Luxmoore 1981, SSSAJ — macro/meso/micro pore-size classes.
            Cameron & Buchan 2006, Encyclopedia of Soil Science — air
                capacity / macroporosity ~5-15% for medium-textured soil.
            Dexter 2004, Geoderma — macropore structure and aggregation.
            Bronick & Lal 2005, Geoderma — aggregation effects on porosity.
        """
        n_layers = len(profile.layers)
        if len(self._state.macro) < n_layers:
            raise ValueError(
                f"PoreNetworkState has {len(self._state.macro)} layers "
                f"but profile has {n_layers}"
            )

        p = self._params
        for i, layer in enumerate(profile.layers):
            total_porosity = layer.saturation

            # --- Drainable pool: pores that empty between saturation and FC.
            # Includes both true macropores (>50 um) and coarse transmission
            # mesopores (10-50 um). Split by sand content (#340).
            drainable = max(0.0, total_porosity - layer.field_capacity)
            sand = TEXTURE_TO_SAND.get(layer.texture, _DEFAULT_SAND_PCT)
            macro_share = min(
                1.0,
                max(0.0, p.macro_split_base + p.macro_split_sand_slope * sand),
            )
            base_macro = macro_share * drainable

            # Meso (plant-available): pores holding water between FC and WP
            meso_available = max(0.0, layer.field_capacity - layer.wilting_point)

            # Residual water: texture-dependent tightly bound water
            # Ref: Rawls 1982 Table 2 — linear fit to θ_r vs clay%
            clay = layer.clay_pct if layer.clay_pct is not None else 22.0
            residual = p.residual_water_intercept + p.residual_water_slope * clay

            # Micro: WP down to residual
            micro = max(0.0, layer.wilting_point - residual)

            # --- Aggregation MWD adjustment ---
            # Well-aggregated soil → more inter-aggregate macropores, drawn
            # from the coarse-mesopore share of the same drainable pool.
            mwd_bonus = 0.0
            if agg_state is not None and i < len(agg_state.macro):
                mwd = agg_state.mwd(i)
                mwd_bonus = p.mwd_macro_coeff * max(0.0, mwd - p.mwd_baseline)

            macro = min(p.max_macro_frac, base_macro + mwd_bonus)
            # Cap at the drainable pool so the coarse-meso remainder stays
            # non-negative; floor at min_macro_frac (but never above pool).
            macro = min(macro, drainable)
            macro = max(macro, min(p.min_macro_frac, drainable))

            # Coarse transmission mesopores: the non-macro part of the pool.
            coarse_meso = max(0.0, drainable - macro)
            meso = meso_available + coarse_meso

            # Crypto = residual: whatever budget remains. macro + meso + micro
            # is guaranteed <= total_porosity, so crypto is non-negative.
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
