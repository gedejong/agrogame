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
from typing import List, Optional

from agrogame.events import EventBus
from agrogame.soil.biopores.events import BioporeCollapsed, BioporeCreated
from agrogame.soil.biopores.params import BioporeParams
from agrogame.soil.biopores.state import BioporeState
from agrogame.soil.models import SoilProfile
from agrogame.soil.pore_network.state import PoreNetworkState


class BioporeModule:
    """Compute biopore creation, decay, and destruction per layer."""

    def __init__(
        self,
        params: BioporeParams,
        state: BioporeState,
        event_bus: Optional[EventBus] = None,
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

    def process_root_turnover(self, per_layer_dead_mass_g_m2: List[float]) -> None:
        """Convert dead-root mass to new biopore density per layer.

        Volume of dead roots = mass / bulk density. A configurable
        ``conversion_factor`` of that volume becomes biopore volume,
        and we back out the number of standard-radius biopores from
        that volume.
        """
        p = self._params
        radius_m = p.mean_radius_mm * 1e-3
        pore_cross_section_m2 = math.pi * radius_m * radius_m
        n = min(len(per_layer_dead_mass_g_m2), len(self._state.density_per_m2))
        for i in range(n):
            dead_mass_g_m2 = per_layer_dead_mass_g_m2[i]
            if dead_mass_g_m2 <= 0.0:
                continue
            # Mass → volume per m² of soil surface (m³/m²).
            # mass_g / density_g_per_cm³ = volume_cm³; ÷ 1e6 → m³.
            dead_volume_m3_per_m2 = (
                dead_mass_g_m2 / max(1e-6, p.root_density_g_per_cm3)
            ) / 1e6
            # Convert to biopore volume per m² of soil surface.
            biopore_volume_m3_per_m2 = dead_volume_m3_per_m2 * p.conversion_factor
            # Number of standard-radius biopores to occupy that volume.
            # A biopore spans the full layer; m³ per pore = π·r²·depth_m.
            # Density = (volume per m² of soil) / (π·r²) — depth cancels
            # because dead_volume_m3_per_m2 was distributed across layer
            # thickness via the dead_mass per layer (caller already split).
            new_density = (
                biopore_volume_m3_per_m2 / pore_cross_section_m2
                if pore_cross_section_m2 > 0
                else 0.0
            )
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
            if half_life <= 0.0 or self._state.density_per_m2[i] <= 0.0:
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

        Only layers that lie (in part) within ``plow_depth_cm`` are
        affected. Deeper layers are untouched, matching the
        ``AggregationModule.apply_tillage`` convention.
        """
        if intensity <= 0.0:
            return
        p = self._params
        intensity = max(0.0, min(1.0, intensity))
        n = min(len(profile.layers), len(self._state.density_per_m2))
        cumulative_depth_cm = 0.0
        for i in range(n):
            layer_top_cm = cumulative_depth_cm
            cumulative_depth_cm += profile.layers[i].depth_cm
            if layer_top_cm >= p.plow_depth_cm:
                break  # subsequent layers are below plow line
            destroy_frac = intensity * p.tillage_destruction_max_frac
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

        Maintains the #211 invariant ``macro + meso + micro + crypto =
        saturation`` by absorbing the bonus from ``crypto`` first, then
        ``micro``, then capping at the available budget. Caller should
        run this after ``PoreNetworkModule.compute()`` for the day.
        """
        n = min(
            len(profile.layers),
            len(pore_state.macro),
            len(self._state.volume_fraction),
        )
        for i in range(n):
            bonus = self._state.volume_fraction[i]
            if bonus <= 0.0:
                continue
            saturation = profile.layers[i].saturation
            current_total = (
                pore_state.macro[i]
                + pore_state.meso[i]
                + pore_state.micro[i]
                + pore_state.crypto[i]
            )
            budget = max(0.0, saturation - current_total)
            # Available = unused budget + crypto + micro (kept as donors).
            absorb_from_crypto = min(pore_state.crypto[i], bonus)
            remaining = bonus - absorb_from_crypto
            absorb_from_micro = min(pore_state.micro[i], remaining)
            remaining -= absorb_from_micro
            absorb_from_budget = min(budget, remaining)
            applied = absorb_from_crypto + absorb_from_micro + absorb_from_budget
            if applied <= 0.0:
                continue
            pore_state.macro[i] += applied
            pore_state.crypto[i] -= absorb_from_crypto
            pore_state.micro[i] -= absorb_from_micro
            # Refresh connectivity (macro / total_porosity).
            new_total = (
                pore_state.macro[i]
                + pore_state.meso[i]
                + pore_state.micro[i]
                + pore_state.crypto[i]
            )
            pore_state.connectivity[i] = (
                min(1.0, max(0.0, pore_state.macro[i] / new_total))
                if new_total > 0.0
                else 0.0
            )

    # --- Helpers ------------------------------------------------------

    def _emit(self, event: object) -> None:
        if self._bus is None:
            return
        self._bus.emit(event)
