"""Runtime wiring for ``GasDiffusionModule`` (#284, ADR-010).

Subscribes to ``DayTick(phase="day_start")`` and runs the steady-state
O₂/CO₂ profile solve, using the freshly computed pore geometry from
:class:`PoreNetworkRuntime` and biopore donations from
:class:`BioporesRuntime`. The resulting ``GasDiffusionState.o2_frac``
and ``anaerobic_microsite_frac`` lists are then read by
:class:`agrogame.soil.redox.runtime.RedoxRuntime` and
:class:`agrogame.soil.nitrogen.runtime.NitrogenRuntime` later in the
same day-tick sequence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.gas_diffusion.module import GasDiffusionModule
from agrogame.soil.models import SoilProfile
from agrogame.soil.pore_network.state import PoreNetworkState
from agrogame.soil.water.state import SoilWaterState


@dataclass
class GasDiffusionRuntime:
    """Bind ``GasDiffusionModule`` to ``DayTick(day_start)``.

    The respiration source term is supplied via a lazily-evaluated
    callable so the orchestrator can plug in the SOM-derived CO₂
    estimate without a hard import dependency on the SOM runtime here.
    The default supplier returns zero respiration — useful for tests
    that exercise the diffusion solver in isolation.
    """

    event_bus: EventBus
    module: GasDiffusionModule
    profile: SoilProfile
    water_state: SoilWaterState
    pore_state: PoreNetworkState
    co2_respiration_supplier: Callable[[int], list[float]] = field(
        default_factory=lambda: lambda n: [0.0] * n
    )

    def __post_init__(self) -> None:
        """Subscribe to DayTick on construction."""
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "day_start":
            return
        n = len(self.profile.layers)
        tmean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        respiration = self.co2_respiration_supplier(n)
        # Defensive: pad/truncate to match layer count so a stale
        # supplier doesn't crash the solver.
        if len(respiration) < n:
            respiration = list(respiration) + [0.0] * (n - len(respiration))
        elif len(respiration) > n:
            respiration = list(respiration[:n])
        self.module.daily_step(
            self.profile,
            list(self.water_state.theta),
            tmean,
            respiration,
            pore_state=self.pore_state,
        )
