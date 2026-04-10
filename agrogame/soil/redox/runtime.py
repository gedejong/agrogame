"""Runtime wiring for RedoxModule to Calendar DayTick events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.redox.module import RedoxModule
from agrogame.plant.roots.events import RootDistributionUpdated


@dataclass
class RedoxRuntime:
    """Bind RedoxModule to the event bus for the 'redox' phase.

    Captures pre-drainage theta (at start of water phase) to compute
    WFPS that reflects actual saturation, before cascade drainage
    removes excess water. This is critical for redox activation —
    the post-drainage theta rarely exceeds field capacity.
    """

    event_bus: EventBus
    module: RedoxModule
    profile: SoilProfile
    water_state: SoilWaterState
    _root_fractions: list[float] | None = None
    _pre_drainage_theta: list[float] | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)

    def _on_root_distribution(self, ev: RootDistributionUpdated) -> None:
        self._root_fractions = list(ev.fractions)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase == "chemistry":
            # Capture theta BEFORE water phase runs. Chemistry phase
            # fires before water, so theta includes irrigation applied
            # before step_day but hasn't been drained yet.
            self._pre_drainage_theta = list(self.water_state.theta)
            return
        if ev.phase != "redox":
            return
        # Use max of pre-drainage and post-drainage theta per layer.
        # Pre-drainage captures irrigation/rainfall; post-drainage is
        # the settled state. Redox responds to the wettest conditions.
        post_theta = list(self.water_state.theta)
        pre = self._pre_drainage_theta or post_theta
        theta = [max(a, b) for a, b in zip(pre, post_theta, strict=False)]
        sat = [ly.saturation for ly in self.profile.layers]
        roots = self._root_fractions or [0.0] * len(theta)
        tmean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        self.module.daily_step(theta, sat, roots, tmean)
