from __future__ import annotations

from typing import Tuple

from agrogame.soil.models import SoilProfile
from agrogame.soil.water.constants import TEXTURE_TO_CN
from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.water.events import (
    EvaporationTaken,
    RunoffGenerated,
    WaterDrained,
    WaterInfiltrated,
)
from agrogame.soil.water.scs import scs_runoff_mm
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers, WaterFluxes


class SoilWaterModel:
    def update_daily(self, profile: SoilProfile, state: SoilWaterState, drivers: DailyDrivers) -> WaterFluxes:  # pragma: no cover - interface
        raise NotImplementedError


class CascadingBucketWaterModel(SoilWaterModel):
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus

    def _texture_cn(self, profile: SoilProfile) -> int:
        texture = profile.layers[0].texture
        return TEXTURE_TO_CN.get(texture, 86)

    def _compute_runoff(self, incoming_mm: float, cn: int) -> Tuple[float, float]:
        runoff = scs_runoff_mm(incoming_mm, cn)
        if self.event_bus and runoff > 0:
            self.event_bus.emit(RunoffGenerated(amount_mm=runoff, curve_number=cn))
        return runoff, incoming_mm - runoff

    def _apply_evaporation(self, profile: SoilProfile, state: SoilWaterState, evaporation_mm: float) -> float:
        if evaporation_mm <= 0:
            return 0.0
        top = state.layer_storage_mm(profile, 0)
        evap_taken = min(evaporation_mm, top)
        if evap_taken > 0:
            state.set_layer_storage_mm(profile, 0, top - evap_taken)
            if self.event_bus:
                self.event_bus.emit(EvaporationTaken(amount_mm=evap_taken))
        return evap_taken

    def _infiltrate_layers(self, profile: SoilProfile, state: SoilWaterState, infiltrated_mm: float) -> float:
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
                WaterInfiltrated(layer_indices=tuple(infil_indices), amounts_mm=tuple(infil_amounts))
            )
        return remaining

    def _cascade_excess(self, profile: SoilProfile, state: SoilWaterState) -> float:
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
                        self.event_bus.emit(WaterDrained(from_layer=i, to_layer=i + 1, amount_mm=moved))
                leftover = excess - moved
                if leftover > 0:
                    deep_drainage += leftover
            else:
                deep_drainage += excess
        return deep_drainage

    def update_daily(self, profile: SoilProfile, state: SoilWaterState, drivers: DailyDrivers) -> WaterFluxes:
        incoming = drivers.rainfall_mm + drivers.irrigation_mm
        cn = self._texture_cn(profile)
        runoff, infiltrated = self._compute_runoff(incoming, cn)

        storage_before = sum(state.layer_storage_mm(profile, i) for i in range(len(profile.layers)))

        evap_taken = self._apply_evaporation(profile, state, drivers.evaporation_mm)
        remaining = self._infiltrate_layers(profile, state, infiltrated)

        deep_drainage = 0.0
        if remaining > 0:
            deep_drainage += remaining

        deep_drainage += self._cascade_excess(profile, state)

        storage_after = sum(state.layer_storage_mm(profile, i) for i in range(len(profile.layers)))
        storage_change = storage_after - storage_before
        return WaterFluxes(
            runoff_mm=runoff,
            deep_drainage_mm=deep_drainage,
            evap_mm=evap_taken,
            storage_change_mm=storage_change,
        )
