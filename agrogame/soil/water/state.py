from __future__ import annotations

from typing import List

from agrogame.soil.models import SoilProfile


class SoilWaterState:
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
