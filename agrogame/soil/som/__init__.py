"""Soil Organic Matter (SOM) module — three-pool decomposition.

RothC-inspired three-pool SOM model (AGRO-103) replacing the SimpleSOMRuntime
placeholder. Tracks labile, intermediate, and stable C/N pools with
temperature/moisture-dependent kinetics, humification, priming, and CO2
tracking.
"""

from agrogame.soil.som.pools import (
    SOMDailyFluxes,
    SOMLayerPool,
    SOMLayerState,
    SOMPoolParams,
    SOMState,
    ThreePoolSOM,
)
from agrogame.soil.som.runtime import SOMRuntime

__all__ = [
    "SOMDailyFluxes",
    "SOMLayerPool",
    "SOMLayerState",
    "SOMPoolParams",
    "SOMState",
    "SOMRuntime",
    "ThreePoolSOM",
]
