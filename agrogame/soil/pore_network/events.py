"""Pore network domain events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import BaseEvent


@dataclass(frozen=True)
class PoreNetworkComputed(BaseEvent):
    """Pore size distribution computed for a soil layer.

    Emitted at initialization and on recomputation (e.g., when
    aggregation state changes).

    Naming (#339): kept as ``PoreNetworkComputed`` rather than renamed to
    ``PoreStructureChanged``. The pore distribution is a *derived
    diagnostic* recomputed from texture and aggregation MWD, not a discrete
    state change, so the ``*Computed`` suffix is the semantically correct
    one under the project's event-tense convention (``docs/conventions.md``
    §"Event tense": ``*Computed`` for derived diagnostics with no state
    mutation; ``*Changed``/``*Updated`` for state changes). The name is also
    an already-shipped, consumed contract (#211/#274/#326); renaming it would
    churn a stable interface for no functional gain.

    Fields (the documented event contract, captured by ``EventRecorder``):
        layer: soil layer index.
        macro/meso/micro/crypto: per-layer volume fractions (m³/m³) that
            sum to the layer's total porosity (saturation).
        connectivity: macropore-fraction structural index in [0, 1].
    """

    layer: int
    macro: float
    meso: float
    micro: float
    crypto: float
    connectivity: float
