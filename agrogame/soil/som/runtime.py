"""SOM runtime — three-pool decomposition wired to the event bus.

Replaces SimpleSOMRuntime with a RothC-inspired three-pool SOM module
that emits SubstrateAvailable and RhizospherePrimingPulse events for
the microbial module, and drives N mineralization from SOM quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.params.ports import SoilProfileView
from agrogame.soil.water.state import SoilWaterState

if TYPE_CHECKING:
    from agrogame.soil.aggregation.state import SoilAggregationState
from agrogame.soil.chemistry.module import SoilChemistryModule
from agrogame.plant.roots.events import RootDistributionUpdated
from agrogame.soil.microbes.events import SubstrateAvailable, RhizospherePrimingPulse
from agrogame.soil.som.pools import ThreePoolSOM, SOMPoolParams
from agrogame.soil.som.events import SOMDecomposed, CO2Respired


@dataclass
class SOMRuntime:
    """Event-driven three-pool SOM runtime.

    Subscribes to DayTick (nutrients phase) and root distribution events.
    Runs daily decomposition per layer, emits substrate availability for
    the microbial module, and updates soil mineral N via the N cycle.
    """

    event_bus: EventBus
    profile: SoilProfileView
    water_state: SoilWaterState
    chemistry: SoilChemistryModule
    som: ThreePoolSOM | None = None
    agg_state: SoilAggregationState | None = None

    def __post_init__(self) -> None:
        n_layers = len(self.profile.layers)
        if self.som is None:
            self.som = ThreePoolSOM(SOMPoolParams(), n_layers)
            self.som.initialize_from_profile(self.profile)
        self._root_fracs: list[float] | None = None
        self._root_fracs_smoothed: list[float] | None = None
        # Wet-dry cycle detection (AGRO-104)
        self._prev_wfps: list[float] = [0.5] * n_layers
        self._was_dry: list[bool] = [False] * n_layers
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

    def _resolve_temperature(self, ev: DayTick) -> float:
        try:
            tmin = float(ev.tmin_c) if ev.tmin_c is not None else 18.0
            tmax = float(ev.tmax_c) if ev.tmax_c is not None else 18.0
            return 0.5 * (tmin + tmax)
        except (TypeError, ValueError):
            return 18.0

    def _check_wet_dry(self, i: int, wfps: float) -> None:
        """Detect wet-dry cycles and trigger aggregate disruption."""
        assert self.som is not None
        p = self.som.params
        prev = self._prev_wfps[i] if i < len(self._prev_wfps) else 0.5
        if prev < p.wet_dry_dry_threshold:
            self._was_dry[i] = True
        if self._was_dry[i] and wfps > p.wet_dry_wet_threshold:
            self.som.apply_wet_dry_disruption(i)
            self._was_dry[i] = False
        self._prev_wfps[i] = wfps

    def _process_layer(self, i: int, temp_c: float, rf: float) -> None:
        """Run SOM decomposition for one layer and emit events."""
        assert self.som is not None
        soil_layer = self.profile.layers[i]
        sat = soil_layer.saturation
        wfps = (
            self.water_state.theta[i] / sat
            if i < len(self.water_state.theta) and sat > 0
            else 0.5
        )
        priming = 1.0 + rf
        clay_pct = getattr(soil_layer, "clay_pct", 22.0) or 22.0
        mwd = self.agg_state.mwd(i) if self.agg_state is not None else 0.0
        self._check_wet_dry(i, wfps)

        fluxes = self.som.daily_step(
            layer_idx=i,
            temp_c=temp_c,
            wfps=wfps,
            priming_multiplier=priming,
            clay_pct=clay_pct,
            mwd_mm=mwd,
        )

        if fluxes.microbial_c_kg_ha > 0:
            self.event_bus.emit(
                SubstrateAvailable(
                    layer=i,
                    available_c_kg_ha=fluxes.microbial_c_kg_ha,
                    quality_index=min(1.0, 0.3 + 0.7 * rf),
                )
            )
        if priming > 1.0:
            self.event_bus.emit(RhizospherePrimingPulse(layer=i, multiplier=priming))
        if fluxes.decomposed_c_kg_ha > 0:
            self.event_bus.emit(
                SOMDecomposed(
                    layer=i,
                    pool="all",
                    decomposed_c_kg_ha=fluxes.decomposed_c_kg_ha,
                    mineralized_n_kg_ha=fluxes.mineralized_n_kg_ha,
                )
            )
        if fluxes.co2_c_kg_ha > 0:
            self.event_bus.emit(CO2Respired(layer=i, co2_c_kg_ha=fluxes.co2_c_kg_ha))

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients" or self.som is None:
            return
        temp_c = self._resolve_temperature(ev)
        root_fracs = self._smooth_root_fracs()
        for i in range(len(self.profile.layers)):
            rf = root_fracs[i] if i < len(root_fracs) else 0.0
            self._process_layer(i, temp_c, rf)
