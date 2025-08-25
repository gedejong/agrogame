from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


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
