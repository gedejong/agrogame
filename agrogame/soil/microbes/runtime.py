from __future__ import annotations

from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from .biomass import MicrobialBiomassModule
from .events import MicrobialSnapshot


@dataclass
class MicrobesRuntime:
    event_bus: EventBus
    microbes: MicrobialBiomassModule

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_day_tick(self, ev: DayTick) -> None:
        # Run microbes during nutrients phase so it aligns with N/P
        if ev.phase != "nutrients":
            return
        temperature = 18.0
        if ev.tmax_c is not None and ev.tmin_c is not None:
            temperature = (float(ev.tmax_c) + float(ev.tmin_c)) / 2.0
        wfps = 0.6
        ph = float(ev.target_ph) if ev.target_ph is not None else 6.8
        self.microbes.daily_step(temperature_c=temperature, wfps=wfps, ph=ph)
        # Emit snapshot for visualization
        total_c = sum(layer.c_kg_ha for layer in self.microbes.state.layers)
        total_n = sum(layer.n_kg_ha for layer in self.microbes.state.layers)
        self.event_bus.emit(
            MicrobialSnapshot(total_c_kg_ha=total_c, total_n_kg_ha=total_n)
        )
