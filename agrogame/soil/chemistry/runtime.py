"""Runtime wiring for ``SoilChemistryModule`` (#288, ADR-010).

Owns every event subscription that drives soil pH: the daily buffering
tick plus the two pH-perturbing events, lime application and the N-cycle
proton load (#492, ADR-020). The module itself subscribes to nothing —
canonical module shape (see ``docs/conventions.md``).

The daily buffering runs on ``DayTick(phase="chemistry")``, which fires
before the water and nutrients phases, so the emitted ``SoilPHUpdated``
values are cached before N/P nitrification consumes them. ``RedoxRuntime``
also keys off the chemistry phase but only reads ``water_state.theta``, so
the relative dispatch order of the two is immaterial.
"""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.soil.nitrogen.events import ProtonLoadOccurred

from .events import LimeApplied
from .module import SoilChemistryModule


@dataclass
class ChemistryRuntime:
    """Bind ``SoilChemistryModule`` to the event bus.

    Holds the subscriptions that formerly lived in
    ``SoilChemistryModule.__init__`` (#288) so the module stays pure logic.
    The P-fixation, nitrate-leaching and acidifying-fertiliser proxies were
    removed in #492: the proton load replaces all three.
    """

    event_bus: EventBus
    module: SoilChemistryModule

    def __post_init__(self) -> None:
        """Subscribe to the pH-relevant events on construction."""
        self.event_bus.subscribe(LimeApplied, self._on_lime)
        self.event_bus.subscribe(ProtonLoadOccurred, self._on_proton_load)
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_lime(self, ev: LimeApplied) -> None:
        self.module.apply_lime(ev.layer, ev.rate_kg_ha)

    def _on_proton_load(self, ev: ProtonLoadOccurred) -> None:
        self.module.apply_proton_load(ev.layer, ev.h_kmol_ha)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "chemistry":
            return
        self.module.daily_step(target_ph=ev.target_ph)
