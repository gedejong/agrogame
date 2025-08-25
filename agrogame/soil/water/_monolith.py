from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, DefaultDict, List, Tuple, Type, TypeVar

from collections import defaultdict

from agrogame.soil.models import SoilProfile


T = TypeVar("T")


class EventBus:
    pass  # moved to agrogame.soil.water.event_bus


# Water events (water-only scope)
@dataclass(frozen=True)
class WaterInfiltrated:  # moved
    layer_indices: Tuple[int, ...]
    amounts_mm: Tuple[float, ...]


@dataclass(frozen=True)
class WaterDrained:  # moved
    from_layer: int
    to_layer: int
    amount_mm: float


@dataclass(frozen=True)
class RunoffGenerated:  # moved
    amount_mm: float
    curve_number: int


@dataclass(frozen=True)
class EvaporationTaken:  # moved
    amount_mm: float


@dataclass(frozen=True)
class WaterFluxes:  # moved
    runoff_mm: float
    deep_drainage_mm: float
    evap_mm: float
    storage_change_mm: float


class DailyDrivers:  # moved
    def __init__(self, rainfall_mm: float, irrigation_mm: float = 0.0, evaporation_mm: float = 0.0):
        self.rainfall_mm = max(0.0, rainfall_mm)
        self.irrigation_mm = max(0.0, irrigation_mm)
        self.evaporation_mm = max(0.0, evaporation_mm)


class SoilWaterState:  # moved
    def __init__(self, profile: SoilProfile):
        self.theta: List[float] = [layer.field_capacity for layer in profile.layers]

    def layer_storage_mm(self, profile: SoilProfile, idx: int) -> float:
        layer = profile.layers[idx]
        return self.theta[idx] * layer.depth_cm * 10.0

    def set_layer_storage_mm(self, profile: SoilProfile, idx: int, storage_mm: float) -> None:
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
}  # moved


def _cn_to_S_mm(cn: int) -> float:  # moved
    return max(0.0, (25400.0 / cn) - 254.0)


def _scs_runoff_mm(precip_mm: float, cn: int) -> float:  # moved
    S = _cn_to_S_mm(cn)
    Ia = 0.2 * S
    if precip_mm <= Ia:
        return 0.0
    return ((precip_mm - Ia) ** 2) / (precip_mm - Ia + S)


class SoilWaterModel:
    pass  # moved to agrogame.soil.water.models.cascading


class CascadingBucketWaterModel:  # moved
    pass


# Backward-compatible wrapper preserving prior API shape
class SoilWaterBalance:  # moved
    pass
