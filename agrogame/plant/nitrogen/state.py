from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlantNitrogenState:
    """Mutable whole-shoot plant-nitrogen state (#360).

    Holds the accumulated shoot N stock plus the most recent diagnostics so
    the orchestrator/frontend can expose the NNI trajectory. The stock is a
    within-season plant property: it starts at zero for a new crop and is
    intentionally *not* persisted in ``SoilSnapshot`` (which captures soil
    pools only). ``reset_crop`` rebuilds this state fresh each season.

    Attributes:
        n_stock_kg_ha: Cumulative N taken up into the whole shoot (kg/ha).
        actual_n_pct: Last computed actual shoot N concentration (% of DM).
        critical_n_pct: Last computed critical N concentration (% of DM).
        nni: Last computed N nutrition index (actual / critical).
        stress: Last emitted N-stress factor in [0, 1] (1 = unstressed).
    """

    n_stock_kg_ha: float = 0.0
    actual_n_pct: float = 0.0
    critical_n_pct: float = 0.0
    nni: float = 1.0
    stress: float = 1.0
