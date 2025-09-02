from __future__ import annotations

from typing import Protocol, runtime_checkable, Sequence


@runtime_checkable
class WaterProfile(Protocol):
    """Abstraction of a soil/water profile for ET extraction.

    Implementations may wrap concrete soil profile structures.
    """

    # Minimal attribute access used by ET for evaporation calculation
    # (duck-typed in implementations)
    ...


@runtime_checkable
class WaterState(Protocol):
    """Abstraction of soil water state for ET extraction operations."""

    def layer_storage_mm(self, profile: WaterProfile, layer_index: int) -> float: ...

    def set_layer_storage_mm(
        self, profile: WaterProfile, layer_index: int, storage_mm: float
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
        transpiration_mm: float,
        root_fractions: Sequence[float],
    ) -> float: ...
