"""Runtime wiring for AggregationModule to Calendar DayTick events."""

from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.aggregation.module import AggregationModule
from agrogame.plant.roots.events import RootDistributionUpdated


@dataclass
class AggregationRuntime:
    """Event-driven aggregation runtime with weekly cadence.

    Runs aggregate formation every 7 days (at day_end phase) and
    responds to tillage events immediately. Tracks wet-dry and
    freeze-thaw cycles for physical breakdown.
    """

    event_bus: EventBus
    module: AggregationModule
    profile: SoilProfile
    water_state: SoilWaterState
    _day_count: int = 0
    _root_fractions: list[float] | None = None
    _fungal_fractions: list[float] | None = None

    def __post_init__(self) -> None:
        n = len(self.profile.layers)
        self._prev_wfps: list[float] = [0.5] * n
        self._was_dry: list[bool] = [False] * n
        self._was_frozen: list[bool] = [False] * n
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)
        # Subscribe to microbial events for fungal fraction
        from agrogame.soil.microbes.events import MicrobialFBUpdated

        self.event_bus.subscribe(MicrobialFBUpdated, self._on_microbes_updated)

    def _on_root_distribution(self, ev: RootDistributionUpdated) -> None:
        self._root_fractions = list(ev.fractions)

    def _on_microbes_updated(self, ev: object) -> None:
        ff = getattr(ev, "fungal_fraction", None)
        layer = getattr(ev, "layer", None)
        if ff is not None and layer is not None:
            n = len(self.profile.layers)
            if self._fungal_fractions is None:
                self._fungal_fractions = [0.3] * n
            if layer < n:
                self._fungal_fractions[layer] = float(ff)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "day_end":
            return

        n = len(self.profile.layers)
        temp_c = self._resolve_temperature(ev)
        rainfall_mm = 0.0
        if ev.drivers is not None:
            rainfall_mm = ev.drivers.rainfall_mm

        # Check physical breakdown processes daily
        self._check_wet_dry(n)
        self._check_freeze_thaw(n, temp_c)

        # Raindrop impact on surface (daily)
        self.module.apply_raindrop_impact(rainfall_mm)

        # Weekly formation step
        self._day_count += 1
        if self._day_count >= 7:
            self._day_count = 0
            roots = self._root_fractions or [0.0] * n
            fungi = self._fungal_fractions or [0.3] * n
            self.module.weekly_step(roots, fungi, temp_c)

    def _check_wet_dry(self, n: int) -> None:
        """Detect wet-dry transitions and apply aggregate breakdown.

        Ref: Denef et al. 2001 — rewetting after dry spell disrupts macro.
        """
        dry_threshold = 0.3
        wet_threshold = 0.7
        for i in range(min(n, len(self._prev_wfps))):
            sat = self.profile.layers[i].saturation
            wfps = (
                self.water_state.theta[i] / sat
                if i < len(self.water_state.theta) and sat > 0
                else 0.5
            )
            if self._prev_wfps[i] < dry_threshold:
                self._was_dry[i] = True
            if self._was_dry[i] and wfps > wet_threshold:
                self.module.apply_wet_dry_breakdown(i)
                self._was_dry[i] = False
            self._prev_wfps[i] = wfps

    def _check_freeze_thaw(self, n: int, temp_c: float) -> None:
        """Detect freeze-thaw transitions and apply aggregate breakdown.

        Ref: Six et al. 2004 — 10–20% per freeze-thaw cycle.
        """
        freeze_temp = self.module.params.freeze_temp_c
        for i in range(min(n, len(self._was_frozen))):
            if temp_c <= freeze_temp:
                self._was_frozen[i] = True
            elif self._was_frozen[i] and temp_c > freeze_temp + 2.0:
                # Thaw detected (with 2°C hysteresis)
                self.module.apply_freeze_thaw_breakdown(i)
                self._was_frozen[i] = False

    @staticmethod
    def _resolve_temperature(ev: DayTick) -> float:
        try:
            tmin = float(ev.tmin_c) if ev.tmin_c is not None else 18.0
            tmax = float(ev.tmax_c) if ev.tmax_c is not None else 18.0
            return 0.5 * (tmin + tmax)
        except (TypeError, ValueError):
            return 18.0
