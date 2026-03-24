"""Cascading bucket soil water model.

Provides a concrete implementation of a simple layer-based water balance with
runoff via SCS CN, infiltration by filling capacity, evaporation from the top
layer, and gravitational drainage cascading through layers.
"""

from __future__ import annotations

from typing import Tuple

from agrogame.soil.models import SoilProfile
from agrogame.soil.water.constants import TEXTURE_TO_CN
from agrogame.events import EventBus
from agrogame.soil.water.events import (
    EvaporationTaken,
    RunoffGenerated,
    WaterDrained,
    WaterInfiltrated,
    TranspirationByLayer,
)
from agrogame.soil.water.scs import scs_runoff_mm
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers, WaterFluxes


class SoilWaterModel:
    """Interface for soil water models."""

    def update_daily(
        self, profile: SoilProfile, state: SoilWaterState, drivers: DailyDrivers
    ) -> WaterFluxes:  # pragma: no cover - interface
        """Advance the water model by one day.

        Args:
            profile: Static soil profile definition.
            state: Mutable state of layer water contents.
            drivers: Exogenous daily drivers (rain/irrigation/evaporation).

        Returns:
            WaterFluxes summarizing the step.
        """
        raise NotImplementedError


class CascadingBucketWaterModel(SoilWaterModel):
    """Concrete cascading bucket implementation."""

    def __init__(self, event_bus: EventBus | None = None):
        """Create the model.

        Args:
            event_bus: Optional bus to emit water events on.
        """
        self.event_bus = event_bus

    def _texture_cn(self, profile: SoilProfile) -> int:
        """Return SCS CN derived from the top layer texture."""
        texture = profile.layers[0].texture
        return TEXTURE_TO_CN.get(texture, 86)

    def _compute_runoff(self, incoming_mm: float, cn: int) -> Tuple[float, float]:
        """Partition incoming water into runoff and infiltrated components."""
        runoff = scs_runoff_mm(incoming_mm, cn)
        if self.event_bus and runoff > 0:
            self.event_bus.emit(RunoffGenerated(amount_mm=runoff, curve_number=cn))
        return runoff, incoming_mm - runoff

    # Expose as public for ET actuator use
    def apply_evaporation(
        self, profile: SoilProfile, state: SoilWaterState, evaporation_mm: float
    ) -> float:
        """Remove actual evaporation from the top layer (bounded by availability)."""
        if evaporation_mm <= 0:
            return 0.0
        top = state.layer_storage_mm(profile, 0)
        evap_taken = min(evaporation_mm, top)
        if evap_taken > 0:
            state.set_layer_storage_mm(profile, 0, top - evap_taken)
            if self.event_bus:
                self.event_bus.emit(EvaporationTaken(amount_mm=evap_taken))
        return evap_taken

    def _infiltrate_layers(
        self, profile: SoilProfile, state: SoilWaterState, infiltrated_mm: float
    ) -> float:
        """Fill layers up to saturation with infiltrated water, top to bottom."""
        remaining = infiltrated_mm
        infil_indices: list[int] = []
        infil_amounts: list[float] = []
        for i, layer in enumerate(profile.layers):
            current = state.layer_storage_mm(profile, i)
            capacity = layer.saturation * layer.depth_cm * 10.0
            room = max(0.0, capacity - current)
            added = min(room, remaining)
            if added > 0:
                state.set_layer_storage_mm(profile, i, current + added)
                infil_indices.append(i)
                infil_amounts.append(added)
            remaining -= added
            if remaining <= 1e-9:
                break
        if self.event_bus and infil_indices:
            self.event_bus.emit(
                WaterInfiltrated(
                    layer_indices=tuple(infil_indices), amounts_mm=tuple(infil_amounts)
                )
            )
        return remaining

    def _cascade_excess(self, profile: SoilProfile, state: SoilWaterState) -> float:
        """Cascade water above field capacity to lower layers or deep drainage."""
        deep_drainage = 0.0
        for i, layer in enumerate(profile.layers):
            current = state.layer_storage_mm(profile, i)
            fc_storage = layer.field_capacity * layer.depth_cm * 10.0
            excess = max(0.0, current - fc_storage)
            if excess <= 1e-9:
                continue
            state.set_layer_storage_mm(profile, i, current - excess)
            if i + 1 < len(profile.layers):
                nxt = state.layer_storage_mm(profile, i + 1)
                nxt_layer = profile.layers[i + 1]
                nxt_capacity = nxt_layer.saturation * nxt_layer.depth_cm * 10.0
                nxt_room = max(0.0, nxt_capacity - nxt)
                moved = min(nxt_room, excess)
                if moved > 0:
                    state.set_layer_storage_mm(profile, i + 1, nxt + moved)
                    if self.event_bus:
                        self.event_bus.emit(
                            WaterDrained(from_layer=i, to_layer=i + 1, amount_mm=moved)
                        )
                leftover = excess - moved
                if leftover > 0:
                    deep_drainage += leftover
            else:
                deep_drainage += excess
        return deep_drainage

    def update_daily(
        self, profile: SoilProfile, state: SoilWaterState, drivers: DailyDrivers
    ) -> WaterFluxes:
        """Run one daily step and return flux diagnostics."""
        incoming = drivers.rainfall_mm + drivers.irrigation_mm
        cn = self._texture_cn(profile)
        runoff, infiltrated = self._compute_runoff(incoming, cn)

        storage_before = sum(
            state.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )

        evap_taken = self.apply_evaporation(profile, state, drivers.evaporation_mm)
        remaining = self._infiltrate_layers(profile, state, infiltrated)

        deep_drainage = 0.0
        if remaining > 0:
            deep_drainage += remaining

        deep_drainage += self._cascade_excess(profile, state)

        storage_after = sum(
            state.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )
        storage_change = storage_after - storage_before
        return WaterFluxes(
            runoff_mm=runoff,
            deep_drainage_mm=deep_drainage,
            evap_mm=evap_taken,
            storage_change_mm=storage_change,
        )

    # --- Plant transpiration extraction ---------------------------------
    @staticmethod
    def _extract_layer(
        profile: SoilProfile,
        state: SoilWaterState,
        layer_idx: int,
        desired_mm: float,
    ) -> float:
        """Extract water from a single layer down to wilting point."""
        layer = profile.layers[layer_idx]
        current = state.layer_storage_mm(profile, layer_idx)
        wilt_storage = layer.wilting_point * layer.depth_cm * 10.0
        available = max(0.0, current - wilt_storage)
        take = min(desired_mm, available)
        if take > 0.0:
            state.set_layer_storage_mm(profile, layer_idx, current - take)
        return take

    def extract_transpiration_by_roots(
        self,
        profile: SoilProfile,
        state: SoilWaterState,
        demand_mm: float,
        root_fractions: tuple[float, ...] | list[float],
    ) -> float:
        """Remove transpiration from layers according to root fractions.

        Water can be extracted down to the wilting point only.

        Args:
            profile: Soil profile.
            state: Current water state (will be mutated).
            demand_mm: Transpiration demand (mm).
            root_fractions: Fractions per layer that sum to 1 across rooted layers.

        Returns:
            Actual transpiration supplied (mm).
        """
        if demand_mm <= 0.0:
            return 0.0
        n = min(len(profile.layers), len(root_fractions))
        if n == 0:
            return 0.0
        s = sum(max(0.0, f) for f in root_fractions[:n]) or 1.0
        shares = [max(0.0, f) / s for f in root_fractions[:n]]

        supplied = 0.0
        layer_indices: list[int] = []
        layer_amounts: list[float] = []
        for i in range(n):
            take = self._extract_layer(profile, state, i, demand_mm * shares[i])
            if take > 0.0:
                supplied += take
                layer_indices.append(i)
                layer_amounts.append(take)
        if self.event_bus and layer_indices:
            self.event_bus.emit(
                TranspirationByLayer(
                    layer_indices=tuple(layer_indices),
                    amounts_mm=tuple(layer_amounts),
                    total_mm=supplied,
                )
            )
        return supplied
