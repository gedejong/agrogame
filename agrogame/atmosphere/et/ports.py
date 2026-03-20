from __future__ import annotations

from typing import Protocol, runtime_checkable, Sequence


class SoilLayer(Protocol):
    """Minimal layer interface needed by ET for topsoil evaporation.

    Concrete soil layer objects should provide these attributes.
    """

    wilting_point: float
    depth_cm: float


@runtime_checkable
class WaterProfile(Protocol):
    """Abstraction of a soil/water profile for ET extraction."""

    layers: Sequence[SoilLayer]


@runtime_checkable
class WaterState(Protocol):
    """Abstraction of soil water state for ET extraction operations."""

    def layer_storage_mm(self, profile: WaterProfile, _layer_index: int) -> float: ...

    def set_layer_storage_mm(
        self, profile: WaterProfile, _layer_index: int, _storage_mm: float
    ) -> None: ...


@runtime_checkable
class TranspirationExtractor(Protocol):
    """Capability to extract transpiration by root distribution.

    Implemented by water models.
    """

    def extract_transpiration_by_roots(
        self,
        profile: WaterProfile,
        state: WaterState,
        _transpiration_mm: float,
        root_fractions: Sequence[float],
    ) -> float: ...


@runtime_checkable
class EvaporationApplier(Protocol):
    """Capability to apply evaporation removal from topsoil."""

    def apply_evaporation(
        self, profile: WaterProfile, state: WaterState, evaporation_mm: float
    ) -> float: ...


@runtime_checkable
class WaterActuator(TranspirationExtractor, Protocol):
    """Composite protocol for water actions used by ET."""

    def apply_evaporation(
        self, profile: WaterProfile, state: WaterState, evaporation_mm: float
    ) -> float: ...
