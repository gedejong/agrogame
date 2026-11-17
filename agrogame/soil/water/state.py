"""Water state representation for soil profile layers."""

from __future__ import annotations


from agrogame.params.ports import SoilProfileView, WaterProfile


class SoilWaterState:
    """Holds volumetric water content state (theta) per layer.

    Theta is initialized at field capacity and expressed as m3/m3.

    Single-domain only: the macropore water domain was retired with the
    dual-porosity model (#466, ADR-016).
    """

    def __init__(self, profile: SoilProfileView):
        """Initialize state with theta set to field capacity per layer.

        Args:
            profile: Soil profile providing layer metadata.
        """
        self.theta: list[float] = [layer.field_capacity for layer in profile.layers]

    def layer_storage_mm(self, profile: WaterProfile, idx: int) -> float:
        """Return water storage of a layer as depth (mm)."""
        layer = profile.layers[idx]
        return self.theta[idx] * layer.depth_cm * 10.0

    def set_layer_storage_mm(
        self, profile: SoilProfileView, idx: int, storage_mm: float
    ) -> None:
        """Set water storage of a layer from depth (mm), clamped to saturation."""
        layer = profile.layers[idx]
        max_storage = layer.saturation * layer.depth_cm * 10.0
        storage_mm = max(0.0, min(storage_mm, max_storage))
        self.theta[idx] = storage_mm / (layer.depth_cm * 10.0)
