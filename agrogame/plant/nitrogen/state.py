from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlantNitrogenState:
    """Mutable whole-shoot plant-nitrogen state (#360).

    Holds the accumulated shoot N stock plus the most recent diagnostics so
    the orchestrator/frontend can expose the NNI trajectory. The stock is a
    within-season plant property: it starts at zero for a new crop and
    ``reset_crop`` rebuilds this state fresh each season. It is persisted
    with the patch's plant state (``FieldManager.to_dict``, alongside the
    canopy, phenology and root state) so a mid-season save resumes the same
    crop (#515), and it is still *not* part of ``SoilSnapshot``, which
    captures soil pools only (ADR-013).

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

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for save files (#515)."""
        return {
            "n_stock_kg_ha": self.n_stock_kg_ha,
            "actual_n_pct": self.actual_n_pct,
            "critical_n_pct": self.critical_n_pct,
            "nni": self.nni,
            "stress": self.stress,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlantNitrogenState:
        """Restore from a plain dict; missing keys take the fresh-crop defaults."""
        return cls(
            n_stock_kg_ha=float(data.get("n_stock_kg_ha", 0.0)),
            actual_n_pct=float(data.get("actual_n_pct", 0.0)),
            critical_n_pct=float(data.get("critical_n_pct", 0.0)),
            nni=float(data.get("nni", 1.0)),
            stress=float(data.get("stress", 1.0)),
        )
