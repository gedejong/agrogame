from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agrogame.events import EventBus
from agrogame.plant.events import NutrientStressComputed, PlantNUptakeComputed

from .module import PlantNitrogenModule
from .state import PlantNitrogenState


@dataclass
class PlantNitrogenRuntime:
    """Wire the whole-shoot plant-N model to the EventBus (#360).

    Subscribes to :class:`PlantNUptakeComputed` (emitted by the nitrogen
    runtime on the ``nutrients`` phase). On each event it accumulates the
    day's soil N uptake into the shoot N stock, reads the current shoot dry
    matter via the injected ``shoot_biomass_provider`` (kept as a callable so
    the plant package never imports ``soil.canopy``), computes the N nutrition
    index, and emits the single graded :class:`NutrientStressComputed` for N.

    This replaces the nitrogen runtime's flow-based (uptake/demand)
    N-stress emission — see :mod:`agrogame.soil.nitrogen.runtime`.
    """

    event_bus: EventBus
    module: PlantNitrogenModule
    state: PlantNitrogenState
    shoot_biomass_provider: Callable[[], float]

    def __post_init__(self) -> None:
        self.event_bus.subscribe(PlantNUptakeComputed, self._on_uptake)

    def _on_uptake(self, ev: PlantNUptakeComputed) -> None:
        shoot_dm_g_m2 = float(self.shoot_biomass_provider())
        stress = self.module.daily_step(
            self.state,
            uptake_kg_ha=float(ev.uptake_kg_ha),
            shoot_dm_g_m2=shoot_dm_g_m2,
        )
        self.event_bus.emit(
            NutrientStressComputed(
                nutrient="N",
                uptake_kg_ha=float(ev.uptake_kg_ha),
                demand_kg_ha=float(ev.demand_kg_ha),
                stress=stress,
            )
        )
