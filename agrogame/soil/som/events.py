"""SOM decomposition diagnostic events."""

from __future__ import annotations

from dataclasses import dataclass
from agrogame.events import BaseEvent


@dataclass(frozen=True)
class SOMDecomposed(BaseEvent):
    """Diagnostic: SOM decomposition occurred in a layer."""

    layer: int
    pool: str  # "labile", "intermediate", "stable"
    decomposed_c_kg_ha: float
    mineralized_n_kg_ha: float


@dataclass(frozen=True)
class CO2Respired(BaseEvent):
    """Diagnostic: CO2 respired from SOM decomposition."""

    layer: int
    co2_c_kg_ha: float
