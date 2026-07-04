from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.events.calendar import DayTick
from agrogame.plant.events import PlantNUptakeComputed
from agrogame.soil.gas_diffusion.state import GasDiffusionState
from agrogame.soil.redox.events import RedoxChanged

from .cycle import NitrogenCycle


@dataclass
class NitrogenRuntime:
    """Wire NitrogenCycle to the EventBus; subscribes to DayTick + RedoxChanged.

    When ``gas_state`` is provided (#284 orchestrator wiring), the
    cycle's aerobic-fraction override is refreshed on every nutrients
    tick from gas-diffusion's ``anaerobic_microsite_frac`` so
    denitrification rates respond to actual O₂ rather than the WFPS
    proxy.

    N stress is *not* computed here (#360). The mass-flow-limited soil N
    uptake is handed off via :class:`PlantNUptakeComputed` to the
    whole-shoot plant-N accounting, which derives the graded NNI-based
    stress. Keeping uptake soil-side and stress plant-side keeps the two
    concerns decoupled.
    """

    event_bus: EventBus
    cycle: NitrogenCycle
    gas_state: GasDiffusionState | None = None
    _eh_by_layer: list[float] | None = None

    def __post_init__(self) -> None:
        """Subscribe to DayTick + RedoxChanged."""
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        self.event_bus.subscribe(RedoxChanged, self._on_redox_changed)

    def _on_redox_changed(self, ev: RedoxChanged) -> None:
        layer = ev.layer
        eh = ev.eh_mv
        if layer is not None and eh is not None:
            if self._eh_by_layer is None:
                self._eh_by_layer = []
            while len(self._eh_by_layer) <= layer:
                self._eh_by_layer.append(200.0)
            self._eh_by_layer[layer] = eh

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        demand = 1.0
        if ev.plant_n_demand_kg_ha is not None:
            demand = float(ev.plant_n_demand_kg_ha)
        tmean = 18.0
        if ev.tmin_c is not None and ev.tmax_c is not None:
            tmean = 0.5 * (float(ev.tmin_c) + float(ev.tmax_c))
        # When gas-diffusion is wired in, refresh the cycle's aerobic-
        # fraction override so denitrification responds to today's O₂
        # profile (#284). Aerobic = 1 - anaerobic_microsite_frac.
        if self.gas_state is not None:
            aerobic = [
                max(0.0, min(1.0, 1.0 - f))
                for f in self.gas_state.anaerobic_microsite_frac
            ]
            self.cycle.set_aerobic_fraction_override(aerobic)
        flux = self.cycle.daily_step(
            temperature_c=tmean,
            plant_demand_kg_ha=demand,
            eh_by_layer=self._eh_by_layer,
        )
        # Hand the day's soil N uptake to the whole-shoot plant-N model,
        # which accumulates the stock and emits the graded NNI stress (#360).
        self.event_bus.emit(
            PlantNUptakeComputed(
                uptake_kg_ha=flux.plant_uptake_kg_ha,
                demand_kg_ha=demand,
            )
        )
