"""Cascading bucket soil water model.

Provides a concrete implementation of a simple layer-based water balance with
runoff via SCS CN, infiltration by filling capacity, evaporation from the top
layer, and gravitational drainage cascading through layers.
"""

from __future__ import annotations


from agrogame.params.ports import SoilProfileView
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
        self, profile: SoilProfileView, state: SoilWaterState, drivers: DailyDrivers
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

    def _texture_cn(self, profile: SoilProfileView) -> int:
        """Return SCS CN derived from the top layer texture."""
        texture = profile.layers[0].texture
        return TEXTURE_TO_CN.get(texture, 86)

    def _compute_runoff(self, incoming_mm: float, cn: int) -> tuple[float, float]:
        """Partition incoming water into runoff and infiltrated components."""
        runoff = scs_runoff_mm(incoming_mm, cn)
        if self.event_bus and runoff > 0:
            self.event_bus.emit(RunoffGenerated(amount_mm=runoff, curve_number=cn))
        return runoff, incoming_mm - runoff

    # Expose as public for ET actuator use
    def apply_evaporation(
        self, profile: SoilProfileView, state: SoilWaterState, evaporation_mm: float
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
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        infiltrated_mm: float,
        porosity_overrides: list[float] | None = None,
    ) -> float:
        """Fill layers up to saturation with infiltrated water, top to bottom."""
        remaining = infiltrated_mm
        infil_indices: list[int] = []
        infil_amounts: list[float] = []
        for i, layer in enumerate(profile.layers):
            current = state.layer_storage_mm(profile, i)
            sat = (
                porosity_overrides[i]
                if porosity_overrides and i < len(porosity_overrides)
                else layer.saturation
            )
            capacity = sat * layer.depth_cm * 10.0
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

    def _drain_saturation_excess(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        porosity_overrides: list[float],
    ) -> float:
        """Pre-pass: expel water exceeding adjusted saturation to deep drainage.

        When aggregation degrades mid-season (B1 fix), porosity may drop below
        current theta — push the excess straight to deep drainage.
        """
        deep_drainage = 0.0
        for i, layer in enumerate(profile.layers):
            if i >= len(porosity_overrides):
                break
            current = state.layer_storage_mm(profile, i)
            sat_cap = porosity_overrides[i] * layer.depth_cm * 10.0
            sat_excess = max(0.0, current - sat_cap)
            if sat_excess <= 1e-9:
                continue
            state.set_layer_storage_mm(profile, i, sat_cap)
            deep_drainage += sat_excess
            if self.event_bus:
                self.event_bus.emit(
                    WaterDrained(from_layer=i, to_layer=-1, amount_mm=sat_excess)
                )
        return deep_drainage

    @staticmethod
    def _layer_capacity(
        profile: SoilProfileView,
        layer_idx: int,
        porosity_overrides: list[float] | None,
    ) -> float:
        """Saturation capacity (mm) for a layer, honouring porosity overrides."""
        layer = profile.layers[layer_idx]
        sat = (
            porosity_overrides[layer_idx]
            if porosity_overrides and layer_idx < len(porosity_overrides)
            else layer.saturation
        )
        return sat * layer.depth_cm * 10.0

    def _drain_fc_excess_to_next_layer(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        layer_idx: int,
        drainable: float,
        porosity_overrides: list[float] | None,
    ) -> float:
        """Move FC-excess from layer_idx into layer_idx+1; return overflow."""
        nxt_idx = layer_idx + 1
        nxt = state.layer_storage_mm(profile, nxt_idx)
        nxt_room = max(
            0.0, self._layer_capacity(profile, nxt_idx, porosity_overrides) - nxt
        )
        moved = min(nxt_room, drainable)
        if moved > 0:
            state.set_layer_storage_mm(profile, nxt_idx, nxt + moved)
            if self.event_bus:
                self.event_bus.emit(
                    WaterDrained(
                        from_layer=layer_idx, to_layer=nxt_idx, amount_mm=moved
                    )
                )
        return drainable - moved

    def _drain_fc_excess_to_deep(self, layer_idx: int, amount_mm: float) -> float:
        """Send FC-excess from layer_idx to deep drainage; emit event."""
        if amount_mm <= 0.0:
            return 0.0
        if self.event_bus:
            self.event_bus.emit(
                WaterDrained(from_layer=layer_idx, to_layer=-1, amount_mm=amount_mm)
            )
        return amount_mm

    def _drain_layer_fc_excess(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        layer_idx: int,
        ksat_factors: list[float] | None,
        porosity_overrides: list[float] | None,
    ) -> float:
        """Drain water above FC for one layer; return deep-drainage contribution.

        Limit drainage by ksat: poorly aggregated soil drains slower.
        ksat_factor < 1 retains some excess above FC (waterlogging).
        Cap at 1.0: in a daily bucket model, the base case already drains
        100% of FC-excess per day. kf > 1 (well-aggregated) cannot accelerate
        beyond instant drainage — benefit manifests as increased
        porosity/capacity instead. Ref: Dexter 2004.
        """
        layer = profile.layers[layer_idx]
        current = state.layer_storage_mm(profile, layer_idx)
        fc_storage = layer.field_capacity * layer.depth_cm * 10.0
        excess = max(0.0, current - fc_storage)
        if excess <= 1e-9:
            return 0.0
        kf = (
            ksat_factors[layer_idx]
            if ksat_factors and layer_idx < len(ksat_factors)
            else 1.0
        )
        drainable = excess * min(1.0, kf)
        retained = excess - drainable
        state.set_layer_storage_mm(profile, layer_idx, fc_storage + retained)
        if layer_idx + 1 < len(profile.layers):
            leftover = self._drain_fc_excess_to_next_layer(
                profile, state, layer_idx, drainable, porosity_overrides
            )
            return self._drain_fc_excess_to_deep(layer_idx, leftover)
        return self._drain_fc_excess_to_deep(layer_idx, drainable)

    def _cascade_excess(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        ksat_factors: list[float] | None = None,
        porosity_overrides: list[float] | None = None,
    ) -> float:
        """Cascade water above field capacity to lower layers or deep drainage."""
        deep_drainage = 0.0
        if porosity_overrides:
            deep_drainage += self._drain_saturation_excess(
                profile, state, porosity_overrides
            )
        for i in range(len(profile.layers)):
            deep_drainage += self._drain_layer_fc_excess(
                profile, state, i, ksat_factors, porosity_overrides
            )
        return deep_drainage

    def update_daily(
        self,
        profile: SoilProfileView,
        state: SoilWaterState,
        drivers: DailyDrivers,
        ksat_factors: list[float] | None = None,
        porosity_overrides: list[float] | None = None,
    ) -> WaterFluxes:
        """Run one daily step and return flux diagnostics."""
        incoming = drivers.rainfall_mm + drivers.irrigation_mm
        cn = self._texture_cn(profile)
        runoff, infiltrated = self._compute_runoff(incoming, cn)

        storage_before = sum(
            state.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )

        evap_taken = self.apply_evaporation(profile, state, drivers.evaporation_mm)
        remaining = self._infiltrate_layers(
            profile, state, infiltrated, porosity_overrides
        )

        deep_drainage = 0.0
        if remaining > 0:
            deep_drainage += remaining

        deep_drainage += self._cascade_excess(
            profile, state, ksat_factors, porosity_overrides
        )

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
        profile: SoilProfileView,
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
        profile: SoilProfileView,
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
