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

from collections.abc import Sequence

from agrogame.events import EventBus

from .events import SoilPHUpdated
from .params import (
    CACO3_G_PER_MOL_CHARGE,
    ChemistryParams,
    LayerBufferProperties,
)
from .state import ChemistryState


class SoilChemistryModule:
    """Per-layer pH state; reacts to lime, fertilizer, and N/P transformations."""

    def __init__(
        self,
        params: ChemistryParams,
        state: ChemistryState,
        event_bus: EventBus,
        layer_properties: Sequence[LayerBufferProperties] | None = None,
    ) -> None:
        self._params = params
        self._state = state
        self.event_bus = event_bus
        self._layer_properties: tuple[LayerBufferProperties, ...] = tuple(
            layer_properties or ()
        )

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

    # --- Lime requirement (pH buffer capacity) ---------------------------
    def ph_buffer_capacity_cmol_kg(self, layer: int) -> float:
        """pH buffer capacity of a layer, cmol(H+)/kg soil per pH unit.

        Rises with clay (saturating) and with organic carbon (linear), the
        two properties that control exchangeable acidity in mineral soils.
        Published pHBC is ~1-2 cmol(H+)/kg/pH on sands, ~3-5 on loams and
        ~5-8 on clays (Curtin & Rostad 1997, Can. J. Soil Sci. 77:621-626;
        Aitken & Moody 1994, Aust. J. Soil Res. 32:975-984).

        Raises:
            ValueError: If no soil properties are configured for ``layer``.
        """
        props = self._layer_props(layer)
        p = self._params
        clay_term = (
            p.phbc_clay_max_cmol_kg
            * props.clay_pct
            / (p.phbc_clay_half_pct + props.clay_pct)
        )
        return clay_term + p.phbc_oc_cmol_per_pct * props.organic_carbon_pct

    def lime_requirement_kg_ha_per_ph(self, layer: int) -> float:
        """CaCO3 needed to raise this layer by one pH unit (kg/ha).

        ``pHBC [cmol(H+)/kg/pH] x 0.01 [mol/cmol] x 50 [g CaCO3 per mol
        charge] x soil mass [kg/ha] / 1000 [g per kg]``. The buffer-method
        basis for lime requirement is Shoemaker, McLean & Pratt (1961),
        SSSAJ 25:274-277.

        Raises:
            ValueError: If no soil properties are configured for ``layer``.
        """
        props = self._layer_props(layer)
        g_caco3_per_kg_soil = (
            0.01 * self.ph_buffer_capacity_cmol_kg(layer) * CACO3_G_PER_MOL_CHARGE
        )
        return g_caco3_per_kg_soil * props.soil_mass_kg_ha / 1000.0

    def apply_lime(self, layer: int, rate_kg_ha: float) -> None:
        """Raise a layer's pH by a buffer-capacity-dependent amount.

        The rate is CaCO3-equivalent kg/ha and is neutralised instantly at
        the daily step; gradual dissolution is tracked separately (#482).
        Non-positive rates are a no-op. pH is capped at ``ph_ceiling``.

        Raises:
            ValueError: If ``layer`` has no configured soil properties.
        """
        if rate_kg_ha <= 0.0:
            return
        delta_ph = rate_kg_ha / self.lime_requirement_kg_ha_per_ph(layer)
        p = self._params
        self._state.ph[layer] = min(p.ph_ceiling, self._state.ph[layer] + delta_ph)
        self._emit_all()

    def _layer_props(self, layer: int) -> LayerBufferProperties:
        if not (0 <= layer < len(self._layer_properties)):
            raise ValueError(
                f"No soil buffer properties for layer {layer}; "
                f"{len(self._layer_properties)} layer(s) configured"
            )
        return self._layer_properties[layer]

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
