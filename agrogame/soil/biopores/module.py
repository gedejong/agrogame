"""Biopore module — root-channel macropore creation, decay, destruction (#215).

Pure logic. Driven by:
- ``RootTurnoverOccurred`` events (creation, via ``process_root_turnover``)
- ``TillageApplied`` events (destruction, via ``apply_tillage``)
- explicit ``apply_compaction`` calls (no event yet — orchestrator-driven)
- daily ``apply_decay`` (exponential half-life per layer)

Refs:
    Kautz 2015, Soil Tillage Res. — biopore persistence + decay.
    Pierret et al. 2007, Plant Soil — biopore density 50-500 /m².
    Six et al. 2004, Plant Soil — root-to-aggregate-to-pore conversion.
    Shipitalo & Butt 1999 — tillage destruction.

Orchestrator wiring + ``SoilSnapshot`` persistence are intentionally
deferred to a follow-up issue, matching the landing order used in
#211/#213/#217.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from agrogame.events import EventBus
from agrogame.soil.biopores.events import BioporeCollapsed, BioporeCreated
from agrogame.soil.biopores.params import BioporeParams
from agrogame.soil.biopores.state import BioporeState
from agrogame.soil.models import SoilProfile
from agrogame.soil.pore_network.state import PoreNetworkState

# Conversion: 1 cm³ = 1e-6 m³.
CM3_TO_M3 = 1e-6


class BioporeModule:
    """Compute biopore creation, decay, and destruction per layer."""

    def __init__(
        self,
        params: BioporeParams,
        state: BioporeState,
        event_bus: EventBus | None = None,
    ) -> None:
        self._params = params
        self._state = state
        self._bus = event_bus

    @property
    def state(self) -> BioporeState:
        return self._state

    @property
    def params(self) -> BioporeParams:
        return self._params

    # --- Creation -----------------------------------------------------

    def process_root_turnover(self, per_layer_dead_mass_g_m2: Sequence[float]) -> None:
        """Convert dead-root mass to new biopore density per layer.

        Volume of dead roots = mass / bulk density. A configurable
        ``conversion_factor`` of that volume becomes biopore volume.
        Density is back-calculated using the **per-layer** mean radius
        (``state.mean_radius_mm[i]``) so that earthworm-augmented layers
        (#76, density-weighted radius) stay mass-consistent.
        """
        p = self._params
        n = min(len(per_layer_dead_mass_g_m2), len(self._state.density_per_m2))
        for i in range(n):
            dead_mass_g_m2 = per_layer_dead_mass_g_m2[i]
            if dead_mass_g_m2 <= 0.0:
                continue
            # Mass → volume per m² of soil surface (m³/m²).
            dead_volume_m3_per_m2 = (
                dead_mass_g_m2 / p.root_density_g_per_cm3 * CM3_TO_M3
            )
            biopore_volume_m3_per_m2 = dead_volume_m3_per_m2 * p.conversion_factor
            # Use the layer's own mean radius for back-calculation —
            # consistent with how volume_fraction is later computed.
            radius_m = self._state.mean_radius_mm[i] * 1e-3
            pore_cross_section_m2 = math.pi * radius_m * radius_m
            if pore_cross_section_m2 <= 0.0:
                continue
            new_density = biopore_volume_m3_per_m2 / pore_cross_section_m2
            if new_density <= 0.0:
                continue
            prev_density = self._state.density_per_m2[i]
            updated = min(p.max_density_per_m2, prev_density + new_density)
            density_delta = updated - prev_density
            if density_delta <= 0.0:
                continue
            self._state.density_per_m2[i] = updated
            self._state.volume_fraction[i] = BioporeState.density_to_volume_fraction(
                updated, self._state.mean_radius_mm[i]
            )
            volume_delta = BioporeState.density_to_volume_fraction(
                density_delta, self._state.mean_radius_mm[i]
            )
            self._emit(
                BioporeCreated(
                    layer=i,
                    density_delta=density_delta,
                    volume_delta=volume_delta,
                )
            )

    # --- Decay --------------------------------------------------------

    def apply_decay(self, profile: SoilProfile) -> None:
        """Daily exponential decay per layer.

        Topsoil layers (cumulative depth ≤ ``topsoil_depth_cm``) use
        the shorter half-life; deeper layers use the subsoil
        half-life. Each layer multiplies density by
        ``0.5 ** (1 / half_life_days)``.
        """
        p = self._params
        n = min(len(profile.layers), len(self._state.density_per_m2))
        cumulative_depth_cm = 0.0
        for i in range(n):
            layer_depth_cm = profile.layers[i].depth_cm
            layer_top_cm = cumulative_depth_cm
            cumulative_depth_cm += layer_depth_cm
            half_life = (
                p.decay_half_life_days_topsoil
                if layer_top_cm < p.topsoil_depth_cm
                else p.decay_half_life_days_subsoil
            )
            if self._state.density_per_m2[i] <= 0.0:
                continue
            survive = 0.5 ** (1.0 / half_life)
            prev = self._state.density_per_m2[i]
            new = prev * survive
            self._state.density_per_m2[i] = new
            self._state.volume_fraction[i] = BioporeState.density_to_volume_fraction(
                new, self._state.mean_radius_mm[i]
            )

    # --- Tillage destruction ------------------------------------------

    def apply_tillage(self, intensity: float, profile: SoilProfile) -> None:
        """Destroy biopores in the plow layer proportional to intensity.

        Effective plow depth scales with intensity (matches
        ``AggregationModule.apply_tillage``: shallow tillage at low
        intensity, full plow depth at intensity=1.0). Each affected
        layer's destroy fraction is further pro-rated by the share of
        layer thickness that lies within the plow zone, so a layer
        straddling the plow line is only partially destroyed.
        """
        if intensity <= 0.0:
            return
        p = self._params
        intensity = max(0.0, min(1.0, intensity))
        effective_plow_depth = p.plow_depth_cm * intensity
        if effective_plow_depth <= 0.0:
            return
        n = min(len(profile.layers), len(self._state.density_per_m2))
        cumulative_depth_cm = 0.0
        for i in range(n):
            layer_top_cm = cumulative_depth_cm
            layer_thickness_cm = profile.layers[i].depth_cm
            layer_bottom_cm = layer_top_cm + layer_thickness_cm
            cumulative_depth_cm = layer_bottom_cm
            if layer_top_cm >= effective_plow_depth:
                break
            # Pro-rate by the share of the layer in the plow zone.
            overlap_cm = max(
                0.0, min(effective_plow_depth, layer_bottom_cm) - layer_top_cm
            )
            overlap_frac = overlap_cm / max(layer_thickness_cm, 1e-9)
            destroy_frac = intensity * p.tillage_destruction_max_frac * overlap_frac
            prev = self._state.density_per_m2[i]
            lost = prev * destroy_frac
            if lost <= 0.0:
                continue
            self._state.density_per_m2[i] = prev - lost
            self._state.volume_fraction[i] = BioporeState.density_to_volume_fraction(
                self._state.density_per_m2[i],
                self._state.mean_radius_mm[i],
            )
            self._emit(BioporeCollapsed(layer=i, cause="tillage", density_lost=lost))

    # --- Compaction ---------------------------------------------------

    def apply_compaction(
        self,
        intensity: float,
        moisture_factor: float,
        profile: SoilProfile,
    ) -> None:
        """Wheel-traffic compaction collapses surface biopores.

        Loss fraction per layer = ``intensity × moisture_factor ×
        compaction_sensitivity``. Wet soils are far more vulnerable
        than dry; ``moisture_factor`` should be 0 (dry) to 1 (saturated).
        Only the surface layer is affected (hooves/tyres mostly compact
        the topmost few cm); subsurface compaction is out of scope.
        """
        if intensity <= 0.0 or moisture_factor <= 0.0:
            return
        if not self._state.density_per_m2 or len(profile.layers) == 0:
            return
        p = self._params
        loss_frac = max(
            0.0,
            min(
                1.0,
                intensity * moisture_factor * p.compaction_sensitivity,
            ),
        )
        if loss_frac <= 0.0:
            return
        prev = self._state.density_per_m2[0]
        lost = prev * loss_frac
        if lost <= 0.0:
            return
        self._state.density_per_m2[0] = prev - lost
        self._state.volume_fraction[0] = BioporeState.density_to_volume_fraction(
            self._state.density_per_m2[0],
            self._state.mean_radius_mm[0],
        )
        self._emit(BioporeCollapsed(layer=0, cause="compaction", density_lost=lost))

    # --- Pore-network integration -------------------------------------

    def update_pore_network(
        self, pore_state: PoreNetworkState, profile: SoilProfile
    ) -> None:
        """Add biopore volume into ``pore_state.macro`` per layer.

        Idempotent across repeated calls within the same compute cycle:
        ``BioporeState.last_applied_volume_fraction`` records the
        previously donated volume per layer, and only the **incremental
        delta** is applied each call. After ``PoreNetworkModule.compute()``
        re-runs, the caller is expected to also reset
        ``last_applied_volume_fraction`` to zero (e.g., via the runtime).

        Maintains the #211 invariant ``macro + meso + micro + crypto =
        saturation`` by absorbing the bonus from ``crypto`` first, then
        ``micro``, then capping at the available budget.

        Negative deltas (biopore volume shrank since last apply) refund
        the macro pool back to crypto/micro proportionally to where it
        was originally taken.
        """
        n = min(
            len(profile.layers),
            len(pore_state.macro),
            len(self._state.volume_fraction),
            len(self._state.last_applied_volume_fraction),
        )
        for i in range(n):
            target = self._state.volume_fraction[i]
            already = self._state.last_applied_volume_fraction[i]
            delta = target - already
            if abs(delta) < 1e-12:
                continue
            if delta > 0.0:
                self._apply_positive_delta(pore_state, profile, i, delta)
            else:
                self._apply_negative_delta(pore_state, i, -delta)
            self._refresh_connectivity(pore_state, i)
            self._state.last_applied_volume_fraction[i] = self._state.volume_fraction[i]

    def reset_pore_network_baseline(self) -> None:
        """Clear ``last_applied_volume_fraction`` after a fresh
        ``PoreNetworkModule.compute()`` resets the donor pools.
        Caller (typically the runtime) invokes this once per compute cycle.
        """
        for i in range(len(self._state.last_applied_volume_fraction)):
            self._state.last_applied_volume_fraction[i] = 0.0

    # --- Helpers ------------------------------------------------------

    def _apply_positive_delta(
        self,
        pore_state: PoreNetworkState,
        profile: SoilProfile,
        layer: int,
        delta: float,
    ) -> None:
        saturation = profile.layers[layer].saturation
        current_total = (
            pore_state.macro[layer]
            + pore_state.meso[layer]
            + pore_state.micro[layer]
            + pore_state.crypto[layer]
        )
        budget = max(0.0, saturation - current_total)
        absorb_from_crypto = min(pore_state.crypto[layer], delta)
        remaining = delta - absorb_from_crypto
        absorb_from_micro = min(pore_state.micro[layer], remaining)
        remaining -= absorb_from_micro
        absorb_from_budget = min(budget, remaining)
        applied = absorb_from_crypto + absorb_from_micro + absorb_from_budget
        if applied <= 0.0:
            return
        pore_state.macro[layer] += applied
        pore_state.crypto[layer] -= absorb_from_crypto
        pore_state.micro[layer] -= absorb_from_micro

    def _apply_negative_delta(
        self,
        pore_state: PoreNetworkState,
        layer: int,
        amount: float,
    ) -> None:
        # Refund: pull from macro back into crypto (the original donor
        # cascade prefers crypto first, so we mirror it on return).
        refund = min(pore_state.macro[layer], amount)
        if refund <= 0.0:
            return
        pore_state.macro[layer] -= refund
        pore_state.crypto[layer] += refund

    @staticmethod
    def _refresh_connectivity(pore_state: PoreNetworkState, layer: int) -> None:
        new_total = (
            pore_state.macro[layer]
            + pore_state.meso[layer]
            + pore_state.micro[layer]
            + pore_state.crypto[layer]
        )
        pore_state.connectivity[layer] = (
            min(1.0, max(0.0, pore_state.macro[layer] / new_total))
            if new_total > 0.0
            else 0.0
        )

    def _emit(self, event: object) -> None:
        if self._bus is None:
            return
        self._bus.emit(event)
