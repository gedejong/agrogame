from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.chemistry.module import SoilChemistryModule
from agrogame.plant.roots.events import RootDistributionUpdated
from agrogame.soil.microbes.events import SubstrateAvailable, RhizospherePrimingPulse


@dataclass
class SimpleSOMRuntime:
    """Placeholder SOM runtime that emits substrate availability per layer.

    This is a stop-gap provider until AGRO-71 lands with real SOM pools.
    """

    event_bus: EventBus
    profile: SoilProfile
    water_state: SoilWaterState
    chemistry: SoilChemistryModule

    def __post_init__(self) -> None:
        self._root_fracs: list[float] | None = None
        self._root_fracs_smoothed: list[float] | None = None
        self.event_bus.subscribe(RootDistributionUpdated, self._on_root_distribution)
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_root_distribution(self, ev: RootDistributionUpdated) -> None:
        fracs = [max(0.0, f) for f in ev.fractions]
        s = sum(fracs) or 1.0
        fracs = [f / s for f in fracs]
        n = len(self.profile.layers)
        if len(fracs) >= n:
            self._root_fracs = fracs[:n]
        else:
            self._root_fracs = fracs + [0.0] * (n - len(fracs))

    def _smooth_root_fracs(self) -> list[float]:
        raw = self._root_fracs or [0.0] * len(self.profile.layers)
        if self._root_fracs_smoothed is None:
            self._root_fracs_smoothed = list(raw)
            return self._root_fracs_smoothed
        alpha = 0.25
        n = len(self._root_fracs_smoothed)
        if len(raw) < n:
            raw = list(raw) + [0.0] * (n - len(raw))
        for i in range(min(len(raw), n)):
            prev = self._root_fracs_smoothed[i]
            cur = raw[i]
            self._root_fracs_smoothed[i] = prev + alpha * (cur - prev)
        return self._root_fracs_smoothed or raw

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        # Simple substrate availability driven by PAR and root fractions
        try:
            par = float(ev.par_mj_m2) if ev.par_mj_m2 is not None else 10.0
        except Exception:
            par = 10.0
        base = 2.0 * (0.6 + 0.04 * max(0.0, min(20.0, par)))
        root_fracs = self._smooth_root_fracs()
        for i in range(len(self.profile.layers)):
            rf = root_fracs[i] if i < len(root_fracs) else 0.0
            available = base * (0.2 + 0.8 * rf)
            quality = 0.6 + 0.3 * rf
            self.event_bus.emit(
                SubstrateAvailable(
                    layer=i, available_c_kg_ha=available, quality_index=quality
                )
            )
            priming = 1.0 + 1.0 * rf
            if priming > 1.0:
                self.event_bus.emit(
                    RhizospherePrimingPulse(layer=i, multiplier=priming)
                )
