"""NitrogenCycle minimal implementation with event subscriptions.

This class wires up to the water module's event bus and provides stubbed
handlers. It enables incremental development and testing of cross-module
integration without committing to full process equations yet.
"""

from __future__ import annotations
from agrogame.soil.water.event_bus import EventBus
from agrogame.soil.water.events import WaterDrained, WaterInfiltrated

from .events import NitrificationOccurred, NutrientLeached
from .state import SoilNitrogenState
from .types import NitrogenFluxes


class NitrogenCycle:
    """Wire nitrogen processes to water events with placeholder logic."""

    def __init__(self, event_bus: EventBus, state: SoilNitrogenState):
        self.event_bus = event_bus
        self.state = state
        self._n_layers = len(state.no3)

        # Subscribe to water movement events
        event_bus.subscribe(WaterDrained, self._on_water_drained)
        event_bus.subscribe(WaterInfiltrated, self._on_infiltrated)

    # --- Event handlers -------------------------------------------------
    def _on_water_drained(self, event: WaterDrained) -> None:
        """Move a proportional fraction of NO3 with drainage water.

        Placeholder: move a fixed fraction (1%) of layer NO3 along the flow.
        """
        from_idx = event.from_layer
        to_idx = event.to_layer
        if 0 <= from_idx < self._n_layers:
            no3_here = self.state.no3[from_idx]
            leached = 0.01 * no3_here
            if leached <= 0.0:
                return
            self.state.no3[from_idx] = max(0.0, no3_here - leached)
            if 0 <= to_idx < self._n_layers:
                self.state.no3[to_idx] += leached
            else:
                # Deep drainage loss
                self.event_bus.emit(
                    NutrientLeached(
                        nutrient="NO3",
                        amount_kg_ha=leached,
                        layer=from_idx,
                    )
                )

    def _on_infiltrated(self, event: WaterInfiltrated) -> None:
        """Placeholder infiltration hook (no-op for now)."""
        return

    # --- Daily update ---------------------------------------------------
    def daily_step(self, temperature_c: float, moisture_rel: float) -> NitrogenFluxes:
        """Compute placeholder daily transformations and return diagnostics.

        This implementation applies tiny fractions to validate wiring:
        - mineralization: 0.05% of organic N -> NH4 (per layer)
        - nitrification: 0.5% of NH4 -> NO3 (per layer)
        - denitrification: 0% (stub)
        - uptake: 0% (stub)
        """
        mineralized = 0.0
        nitrified = 0.0

        # Mineralization
        for i in range(self._n_layers):
            org = self.state.organic_n[i]
            if org > 0.0:
                d = 0.0005 * org
                self.state.organic_n[i] -= d
                self.state.nh4[i] += d
                mineralized += d

        # Nitrification
        for i in range(self._n_layers):
            nh4 = self.state.nh4[i]
            if nh4 > 0.0:
                d = 0.005 * nh4
                self.state.nh4[i] -= d
                self.state.no3[i] += d
                nitrified += d
                self.event_bus.emit(NitrificationOccurred(layer=i, amount_kg_ha=d))

        return NitrogenFluxes(
            mineralized_kg_ha=mineralized,
            nitrified_kg_ha=nitrified,
            denitrified_kg_ha=0.0,
            plant_uptake_kg_ha=0.0,
            leached_kg_ha=0.0,
        )
