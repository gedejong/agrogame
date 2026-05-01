"""Runtime wiring for BioporeModule (#215)."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.plant.roots.events import RootTurnoverOccurred
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.aggregation.events import TillageApplied
from agrogame.soil.biopores.module import BioporeModule
from agrogame.soil.models import SoilProfile


@dataclass
class BioporesRuntime:
    """Bind ``BioporeModule`` to the event bus.

    Subscriptions:
    - ``DayTick`` (phase ``"day_end"``): apply daily decay
    - ``RootTurnoverOccurred``: convert dead roots to biopores
    - ``TillageApplied``: destroy plow-depth biopores

    Compaction is not event-driven yet — orchestrator must call
    ``module.apply_compaction(...)`` directly after wheel-traffic
    actions until a `CompactionApplied` event exists.
    """

    event_bus: EventBus
    module: BioporeModule
    profile: SoilProfile

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(RootTurnoverOccurred, self._on_root_turnover)
        self.event_bus.subscribe(TillageApplied, self._on_tillage)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "day_end":
            return
        self.module.apply_decay(self.profile)

    def _on_root_turnover(self, ev: RootTurnoverOccurred) -> None:
        self.module.process_root_turnover(list(ev.per_layer_dead_mass_g_m2))

    def _on_tillage(self, ev: TillageApplied) -> None:
        self.module.apply_tillage(ev.intensity, self.profile)
