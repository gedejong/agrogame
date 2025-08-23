from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, DefaultDict, List, Tuple, Type, TypeVar

from collections import defaultdict

from agrogame.soil.models import SoilProfile


T = TypeVar("T")


class EventBus:
    def __init__(self, debug_mode: bool = False):
        self._handlers: DefaultDict[type, List[Callable[[Any], None]]] = defaultdict(
            list
        )
        self._debug_mode = debug_mode

    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        self._handlers[event_type].append(handler)

    def emit(self, event: Any) -> None:
        for handler in list(self._handlers[type(event)]):
            try:
                handler(event)
            except Exception as e:  # pragma: no cover
                if self._debug_mode:
                    raise
                # best‑effort isolation; logging can be added later
                _ = e


# Water events (water-only scope)
@dataclass(frozen=True)
class WaterInfiltrated:
    layer_indices: Tuple[int, ...]
    amounts_mm: Tuple[float, ...]


@dataclass(frozen=True)
class WaterDrained:
    from_layer: int
    to_layer: int
    amount_mm: float


@dataclass(frozen=True)
class RunoffGenerated:
    amount_mm: float
    curve_number: int


@dataclass(frozen=True)
class EvaporationTaken:
    amount_mm: float


@dataclass(frozen=True)
class WaterFluxes:
    runoff_mm: float
    deep_drainage_mm: float
    evap_mm: float
    storage_change_mm: float


class DailyDrivers:
    def __init__(
        self,
        rainfall_mm: float,
        irrigation_mm: float = 0.0,
        evaporation_mm: float = 0.0,
    ):
        self.rainfall_mm = max(0.0, rainfall_mm)
        self.irrigation_mm = max(0.0, irrigation_mm)
        self.evaporation_mm = max(0.0, evaporation_mm)


class SoilWaterState:
    def __init__(self, profile: SoilProfile):
        self.theta: List[float] = [layer.field_capacity for layer in profile.layers]

    def layer_storage_mm(self, profile: SoilProfile, idx: int) -> float:
        layer = profile.layers[idx]
        return self.theta[idx] * layer.depth_cm * 10.0

    def set_layer_storage_mm(
        self, profile: SoilProfile, idx: int, storage_mm: float
    ) -> None:
        layer = profile.layers[idx]
        max_storage = layer.saturation * layer.depth_cm * 10.0
        storage_mm = max(0.0, min(storage_mm, max_storage))
        self.theta[idx] = storage_mm / (layer.depth_cm * 10.0)


TEXTURE_TO_CN = {
    "sand": 77,
    "sandy_loam": 79,
    "loam": 86,
    "clay_loam": 89,
    "clay": 91,
    "peat": 85,
}


def _cn_to_S_mm(cn: int) -> float:
    return max(0.0, (25400.0 / cn) - 254.0)


def _scs_runoff_mm(precip_mm: float, cn: int) -> float:
    S = _cn_to_S_mm(cn)
    Ia = 0.2 * S
    if precip_mm <= Ia:
        return 0.0
    return ((precip_mm - Ia) ** 2) / (precip_mm - Ia + S)


class SoilWaterModel:
    def update_daily(
        self, profile: SoilProfile, state: SoilWaterState, drivers: DailyDrivers
    ) -> WaterFluxes:  # pragma: no cover - interface
        raise NotImplementedError


class CascadingBucketWaterModel(SoilWaterModel):
    def __init__(self, event_bus: EventBus | None = None):
        self.event_bus = event_bus

    def _texture_cn(self, profile: SoilProfile) -> int:
        texture = profile.layers[0].texture
        return TEXTURE_TO_CN.get(texture, 86)

    def update_daily(
        self, profile: SoilProfile, state: SoilWaterState, drivers: DailyDrivers
    ) -> WaterFluxes:
        incoming = drivers.rainfall_mm + drivers.irrigation_mm
        cn = self._texture_cn(profile)
        runoff = _scs_runoff_mm(incoming, cn)
        infiltrated = incoming - runoff
        if self.event_bus and runoff > 0:
            self.event_bus.emit(RunoffGenerated(amount_mm=runoff, curve_number=cn))

        storage_before = sum(
            state.layer_storage_mm(profile, i) for i in range(len(profile.layers))
        )

        # Evaporation from top layer
        evap_taken = 0.0
        if drivers.evaporation_mm > 0:
            top = state.layer_storage_mm(profile, 0)
            evap_taken = min(drivers.evaporation_mm, top)
            state.set_layer_storage_mm(profile, 0, top - evap_taken)
            if self.event_bus and evap_taken > 0:
                self.event_bus.emit(EvaporationTaken(amount_mm=evap_taken))

        # Infiltrate into layers up to saturation
        remaining = infiltrated
        infil_indices: List[int] = []
        infil_amounts: List[float] = []
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

        deep_drainage = 0.0
        # If still remaining beyond saturation, it's deep drainage
        if remaining > 0:
            deep_drainage += remaining

        # Cascade excess over field capacity downward
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


# Backward-compatible wrapper preserving prior API shape
class SoilWaterBalance:
    def __init__(self, profile: SoilProfile, event_bus: EventBus | None = None):
        self.profile = profile
        self._state = SoilWaterState(profile)
        self._model = CascadingBucketWaterModel(event_bus=event_bus)
        self.last_runoff_mm: float = 0.0
        self.last_deep_drainage_mm: float = 0.0
        self.last_evap_mm: float = 0.0

    def update_daily(
        self,
        rainfall_mm: float,
        irrigation_mm: float = 0.0,
        evaporation_mm: float = 0.0,
    ) -> Tuple[float, float, float]:
        flux = self._model.update_daily(
            self.profile,
            self._state,
            DailyDrivers(
                rainfall_mm=rainfall_mm,
                irrigation_mm=irrigation_mm,
                evaporation_mm=evaporation_mm,
            ),
        )
        self.last_runoff_mm = flux.runoff_mm
        self.last_deep_drainage_mm = flux.deep_drainage_mm
        self.last_evap_mm = flux.evap_mm
        return flux.runoff_mm, flux.deep_drainage_mm, flux.storage_change_mm
