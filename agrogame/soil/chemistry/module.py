"""Lightweight soil chemistry dynamics to emit pH updates as events.

This module is intentionally simple: it integrates daily pH tendencies from
fertilizer additions, leaching, and a slow buffering term and emits
`SoilPHUpdated` per layer. Nutrient modules can subscribe to use per-layer pH
without tight coupling.
"""

from __future__ import annotations


from agrogame.events import EventBus
from agrogame.soil.nitrogen.events import NutrientLeached
from agrogame.soil.phosphorus.events import PhosphorusFixationOccurred
from .events import SoilPHUpdated, LimeApplied, AcidifyingFertilizerApplied
from agrogame.sim.calendar_events import DayTick


class SoilChemistryModule:
    """Per-layer pH state; reacts to lime, fertilizer, and N/P transformations."""

    def __init__(self, event_bus: EventBus, n_layers: int, base_ph: float = 6.8):
        self.event_bus = event_bus
        self._ph: list[float] = [float(base_ph)] * n_layers
        # Subscribe to relevant events that may influence pH
        event_bus.subscribe(NutrientLeached, self._on_nutrient_leached)
        event_bus.subscribe(PhosphorusFixationOccurred, self._on_p_fix)
        event_bus.subscribe(LimeApplied, self._on_lime)
        event_bus.subscribe(AcidifyingFertilizerApplied, self._on_acid_fert)
        # Subscribe to calendar ticks to run daily buffering in a phased manner
        event_bus.subscribe(DayTick, self._on_day_tick)

    def _emit_all(self) -> None:
        for i, ph in enumerate(self._ph):
            self.event_bus.emit(SoilPHUpdated(layer=i, ph=ph))

    # Simplified heuristics: nitrate leaching tends to acidify slightly; fixation
    # implies reactions with Fe/Al oxides that can reduce availability under low pH.
    def _on_nutrient_leached(self, ev: NutrientLeached) -> None:  # pragma: no cover
        if ev.nutrient.upper() == "NO3":
            self._ph[ev.layer] = max(4.0, self._ph[ev.layer] - 0.005)
            self._emit_all()

    def _on_p_fix(self, ev: PhosphorusFixationOccurred) -> None:  # pragma: no cover
        # Tiny local acidification proxy when fixation occurs
        idx = ev.layer
        self._ph[idx] = max(4.0, self._ph[idx] - 0.002)
        self._emit_all()

    def _on_lime(self, ev: LimeApplied) -> None:  # pragma: no cover
        idx = ev.layer
        # Simple neutralization: raise pH proportionally (capped)
        self._ph[idx] = min(9.0, self._ph[idx] + 0.001 * ev.rate_kg_ha)
        self._emit_all()

    def _on_acid_fert(
        self, ev: AcidifyingFertilizerApplied
    ) -> None:  # pragma: no cover
        idx = ev.layer
        self._ph[idx] = max(4.0, self._ph[idx] - 0.0005 * ev.rate_kg_ha)
        self._emit_all()

    def _on_day_tick(self, ev: DayTick) -> None:
        """Handle calendar DayTick events.

        Runs daily buffering during the 'chemistry' phase using the provided
        target_ph if available, otherwise defaults to 6.8.
        """
        if ev.phase != "chemistry":
            return
        target = 6.8 if ev.target_ph is None else float(ev.target_ph)
        self.daily_buffering(target_ph=target)

    def daily_buffering(self, target_ph: float = 6.8, rate: float = 0.001) -> None:
        """Apply a weak buffering tendency towards target_pH each day."""
        for i, ph in enumerate(self._ph):
            self._ph[i] = ph + rate * (target_ph - ph)
        self._emit_all()

    @property
    def ph_by_layer(self) -> list[float]:
        return list(self._ph)
