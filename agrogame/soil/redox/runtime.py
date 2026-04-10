"""Runtime wiring for RedoxModule to Calendar DayTick events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.redox.module import RedoxModule


@dataclass
class RedoxRuntime:
    """Bind RedoxModule to the event bus for the 'redox' phase."""

    event_bus: EventBus
    module: RedoxModule
    profile: SoilProfile
    water_state: SoilWaterState
    _root_fractions: list[float] | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        # Listen for root distribution updates
        from agrogame.plant.roots.events import RootDistributionUpdated

        self.event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)

    def _on_root_distribution(self, ev: object) -> None:
        fracs = getattr(ev, "fractions", None)
        if fracs is not None:
            self._root_fractions = list(fracs)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "redox":
            return
        theta = list(self.water_state.theta)
        sat = [ly.saturation for ly in self.profile.layers]
        roots = self._root_fractions or [0.0] * len(theta)
        tmean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        self.module.daily_step(theta, sat, roots, tmean)
