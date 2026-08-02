"""Runtime wiring for ``SoilChemistryModule`` (#288, ADR-010).

Owns every event subscription that drives soil pH: the daily buffering
tick plus the four pH-perturbing events (nitrate leaching, phosphorus
fixation, lime application, acidifying-fertilizer application). The module
itself subscribes to nothing — canonical module shape (see
``docs/conventions.md``).

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
from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.soil.phosphorus.events import PhosphorusFixationOccurred

from .events import AcidifyingFertilizerApplied, LimeApplied
from .module import SoilChemistryModule


@dataclass
class ChemistryRuntime:
    """Bind ``SoilChemistryModule`` to the event bus.

    Relocates the five subscriptions that formerly lived in
    ``SoilChemistryModule.__init__`` (#288) so the module stays pure logic.
    """

    event_bus: EventBus
    module: SoilChemistryModule

    def __post_init__(self) -> None:
        """Subscribe to the pH-relevant events on construction."""
        self.event_bus.subscribe(NutrientLeached, self._on_nutrient_leached)
        self.event_bus.subscribe(PhosphorusFixationOccurred, self._on_p_fix)
        self.event_bus.subscribe(LimeApplied, self._on_lime)
        self.event_bus.subscribe(AcidifyingFertilizerApplied, self._on_acid_fert)
        self.event_bus.subscribe(DayTick, self._on_day_tick)

    def _on_nutrient_leached(self, ev: NutrientLeached) -> None:
        self.module.apply_nutrient_leaching(ev.nutrient, ev.layer)

    def _on_p_fix(self, ev: PhosphorusFixationOccurred) -> None:
        self.module.apply_phosphorus_fixation(ev.layer)

    def _on_lime(self, ev: LimeApplied) -> None:
        self.module.apply_lime(ev.layer, ev.rate_kg_ha)

    def _on_acid_fert(self, ev: AcidifyingFertilizerApplied) -> None:
        self.module.apply_acidifying_fertilizer(ev.layer, ev.rate_kg_ha)

    def _on_day_tick(self, ev: DayTick) -> None:
        if ev.phase != "chemistry":
            return
        self.module.daily_step(target_ph=ev.target_ph)
