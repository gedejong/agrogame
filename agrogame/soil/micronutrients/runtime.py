"""Runtime wiring for MicronutrientCycle to Calendar DayTick events."""

from __future__ import annotations

from dataclasses import dataclass, field

from agrogame.events import EventBus
from agrogame.sim.calendar_events import DayTick
from agrogame.soil.micronutrients.cycle import MicronutrientCycle
from agrogame.soil.micronutrients.params import RedoxMicronutrientParams
from agrogame.soil.redox.events import RedoxChanged


@dataclass
class MicronutrientRuntime:
    """Bind MicronutrientCycle to the event bus for the 'nutrients' phase."""

    event_bus: EventBus
    cycle: MicronutrientCycle
    redox_params: RedoxMicronutrientParams = field(
        default_factory=RedoxMicronutrientParams
    )
    _last_biomass_inc: float = 0.0
    _root_fractions: list[float] | None = None

    def __post_init__(self) -> None:
        self.event_bus.subscribe(DayTick, self._on_day_tick)
        from agrogame.soil.canopy.events import BiomassAccumulated
        from agrogame.plant.roots.events import RootDistributionUpdated

        self.event_bus.subscribe(BiomassAccumulated, self._on_biomass)
        self.event_bus.subscribe(RootDistributionUpdated, self._on_roots)
        self.event_bus.subscribe(RedoxChanged, self._on_redox_changed)

    def _on_biomass(self, ev: object) -> None:
        inc = getattr(ev, "increment_g_m2", None)
        if inc is not None:
            self._last_biomass_inc = float(inc)

    def _on_roots(self, ev: object) -> None:
        fracs = getattr(ev, "fractions", None)
        if fracs is not None:
            self._root_fractions = list(fracs)

    def _on_redox_changed(self, ev: RedoxChanged) -> None:
        """Shift Fe/Mn pools based on Eh (#216).

        Ref: Patrick & Reddy 1976 (Fe); Stumm & Morgan 1996 (Mn).
        """
        self.cycle.apply_redox_adjustment(
            layer=ev.layer,
            eh_mv=ev.eh_mv,
            redox_params=self.redox_params,
        )

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "nutrients":
            return
        self.cycle.daily_step(
            biomass_inc_g_m2=self._last_biomass_inc,
            root_fractions=self._root_fractions,
        )
