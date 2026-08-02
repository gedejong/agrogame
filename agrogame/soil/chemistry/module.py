"""Lightweight soil chemistry dynamics to emit pH updates as events.

This module is intentionally simple: it integrates daily pH tendencies from
fertilizer additions, leaching, and a slow buffering term and emits
`SoilPHUpdated` per layer. Nutrient modules can subscribe to use per-layer pH
without tight coupling.

Canonical module shape (#288): pure logic over ``ChemistryParams`` +
``ChemistryState``. The module subscribes to no events itself — the
:class:`agrogame.soil.chemistry.runtime.ChemistryRuntime` owns the event
wiring and dispatches to the public ``apply_*`` methods and ``daily_step``.
"""

from __future__ import annotations

from agrogame.events import EventBus

from .events import SoilPHUpdated
from .params import ChemistryParams
from .state import ChemistryState


class SoilChemistryModule:
    """Per-layer pH state; reacts to lime, fertilizer, and N/P transformations."""

    def __init__(
        self,
        params: ChemistryParams,
        state: ChemistryState,
        event_bus: EventBus,
    ) -> None:
        self._params = params
        self._state = state
        self.event_bus = event_bus

    @property
    def state(self) -> ChemistryState:
        return self._state

    def set_state(self, state: ChemistryState) -> None:
        """Replace state contents in place to preserve aliases.

        Runtimes and the orchestrator hold references to this module (and
        thus its ``ChemistryState``). Mutating the pH list in place keeps
        those references valid after a snapshot restore.
        """
        self._state.ph = list(state.ph)

    def _emit_all(self) -> None:
        for i, ph in enumerate(self._state.ph):
            self.event_bus.emit(SoilPHUpdated(layer=i, ph=ph))

    # Simplified heuristics: nitrate leaching tends to acidify slightly; fixation
    # implies reactions with Fe/Al oxides that can reduce availability under low pH.
    def apply_nutrient_leaching(self, nutrient: str, layer: int) -> None:
        """Acidify a layer slightly on nitrate (NO3) leaching."""
        if nutrient.upper() != "NO3":
            return
        p = self._params
        self._state.ph[layer] = max(
            p.ph_floor, self._state.ph[layer] - p.no3_leach_ph_delta
        )
        self._emit_all()

    def apply_phosphorus_fixation(self, layer: int) -> None:
        """Tiny local acidification proxy when P fixation occurs."""
        p = self._params
        self._state.ph[layer] = max(
            p.ph_floor, self._state.ph[layer] - p.p_fixation_ph_delta
        )
        self._emit_all()

    def apply_lime(self, layer: int, rate_kg_ha: float) -> None:
        """Simple neutralization: raise pH proportionally (capped)."""
        p = self._params
        self._state.ph[layer] = min(
            p.ph_ceiling,
            self._state.ph[layer] + p.lime_ph_delta_per_kg_ha * rate_kg_ha,
        )
        self._emit_all()

    def apply_acidifying_fertilizer(self, layer: int, rate_kg_ha: float) -> None:
        """Lower pH proportionally to the acidifying-fertilizer rate (floored)."""
        p = self._params
        self._state.ph[layer] = max(
            p.ph_floor,
            self._state.ph[layer] - p.acidifying_ph_delta_per_kg_ha * rate_kg_ha,
        )
        self._emit_all()

    def daily_step(self, target_ph: float | None = None) -> None:
        """Apply a weak buffering tendency towards ``target_ph`` each day.

        Falls back to ``params.default_target_ph`` when no target is given.
        """
        p = self._params
        target = p.default_target_ph if target_ph is None else float(target_ph)
        for i, ph in enumerate(self._state.ph):
            self._state.ph[i] = ph + p.buffering_rate * (target - ph)
        self._emit_all()

    @property
    def ph_by_layer(self) -> list[float]:
        return list(self._state.ph)
