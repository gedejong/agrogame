"""Pore network domain events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class PoreNetworkComputed(BaseEvent):
    """Pore size distribution computed for a soil layer.

    Emitted at initialization and on recomputation (e.g., when
    aggregation state changes).
    """

    layer: int
    macro: float
    meso: float
    micro: float
    crypto: float
    connectivity: float
