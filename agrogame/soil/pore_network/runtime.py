"""Runtime wiring for ``PoreNetworkModule`` (#284, ADR-010).

Subscribes to ``DayTick(phase="day_start")`` and recomputes the pore
size distribution from the current soil profile and aggregation state.
This must run **before** :meth:`BioporeModule.update_pore_network` (which
donates biopore volume into ``macro``) and **before**
:meth:`GasDiffusionModule.daily_step` (which reads the refined pore
geometry). Subscription order in the orchestrator's ``_wire_runtimes``
preserves that order — see ADR-010.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.models import SoilProfile
from agrogame.soil.pore_network.module import PoreNetworkModule

if TYPE_CHECKING:
    from agrogame.soil.biopores.module import BioporeModule


@dataclass
class PoreNetworkRuntime:
    """Bind ``PoreNetworkModule`` to ``DayTick(day_start)``.

    Each tick re-derives the pore distribution and clears the biopore
    runtime's "last applied" baseline so the next biopore donation
    reflects the freshly recomputed ``macro`` pool rather than
    accumulating stale deltas.
    """

    event_bus: EventBus
    module: PoreNetworkModule
    profile: SoilProfile
    agg_state: SoilAggregationState | None = None
    # Optional reference so we can reset the donation baseline atomically
    # with the pore_network recompute. The orchestrator wires this in.
    # Typed via TYPE_CHECKING to avoid a runtime import edge from
    # pore_network → biopores (the reverse direction already exists:
    # biopores.module imports pore_network.state).
    biopore_module: BioporeModule | None = None

    def __post_init__(self) -> None:
        """Subscribe to DayTick on construction."""
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "day_start":
            return
        self.module.compute(self.profile, self.agg_state)
        # Reset biopore donation baseline: PoreNetworkModule.compute
        # zeroed-then-rebuilt the macro pool, so any prior biopore
        # donation has been wiped. The biopore module's
        # `last_applied_volume_fraction` must therefore be zeroed too,
        # otherwise its next donation would be a (target - stale_applied)
        # delta rather than a fresh full-volume contribution.
        if self.biopore_module is not None:
            self.biopore_module.reset_pore_network_baseline()
