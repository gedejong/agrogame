"""Water state representation for soil profile layers."""

from __future__ import annotations

from typing import List, Optional

from agrogame.soil.models import SoilProfile


class SoilWaterState:
    """Holds volumetric water content state (theta) per layer.

    Theta is initialized at field capacity and expressed as m3/m3.

    Dual-porosity extension (#213): ``theta_macro`` holds the volumetric
    water content in the macropore domain (m3/m3 of bulk soil volume).
    When None, the model operates in single-domain mode (backward compat).
    Enable via ``enable_dual_porosity()`` before using a dual-porosity
    water model.
    """

    def __init__(self, profile: SoilProfile):
        """Initialize state with theta set to field capacity per layer.

        Args:
            profile: Soil profile providing layer metadata.
        """
        self.theta: List[float] = [layer.field_capacity for layer in profile.layers]
        self.theta_macro: Optional[List[float]] = None

    def enable_dual_porosity(self, n_layers: int) -> None:
        """Initialize empty macropore domain state (all layers at theta=0)."""
        self.theta_macro = [0.0] * n_layers

    def layer_storage_mm(self, profile: SoilProfile, idx: int) -> float:
        """Return water storage of a layer as depth (mm)."""
        layer = profile.layers[idx]
        return self.theta[idx] * layer.depth_cm * 10.0

    def set_layer_storage_mm(
        self, profile: SoilProfile, idx: int, storage_mm: float
    ) -> None:
        """Set water storage of a layer from depth (mm), clamped to saturation."""
        layer = profile.layers[idx]
        max_storage = layer.saturation * layer.depth_cm * 10.0
        storage_mm = max(0.0, min(storage_mm, max_storage))
        self.theta[idx] = storage_mm / (layer.depth_cm * 10.0)
