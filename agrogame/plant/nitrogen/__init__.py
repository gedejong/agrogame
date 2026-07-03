"""Whole-shoot plant-nitrogen accounting (#360).

A stock-based critical-N dilution model that turns the mass-flow-limited
soil N uptake into a *graded* growth response, replacing the bimodal
flow-based (uptake/demand) N-stress proxy.

The plant accumulates soil N uptake into a whole-shoot N stock (kg/ha).
Each day the stock and the shoot dry matter give an actual shoot N
concentration, which is compared against the critical-N dilution curve
``N_crit% = a * W^-b`` (Lemaire & Gastal 1997; Justes et al. 1994;
Plénet & Lemaire 1999). The ratio is the N nutrition index (NNI); a
documented NNI->stress mapping produces a continuous stress factor that
the canopy folds into its Liebig minimum on RUE.

See ADR-012 for the whole-shoot vs per-organ decision and the placement
of this cross-community layer.
"""

from __future__ import annotations

from .module import PlantNitrogenModule
from .params import PlantNitrogenParams
from .runtime import PlantNitrogenRuntime
from .state import PlantNitrogenState

__all__ = [
    "PlantNitrogenModule",
    "PlantNitrogenParams",
    "PlantNitrogenRuntime",
    "PlantNitrogenState",
]
