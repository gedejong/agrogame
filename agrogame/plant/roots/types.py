from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass
class RootState:
    """Mutable per-day root state: depth, biomass, per-layer fractions."""

    current_depth_cm: float = 5.0
    biomass_g_m2: float = 0.0
    layer_fractions: List[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_depth_cm": self.current_depth_cm,
            "biomass_g_m2": self.biomass_g_m2,
            "layer_fractions": (
                list(self.layer_fractions) if self.layer_fractions else []
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RootState:
        fracs = data.get("layer_fractions", [])
        return cls(
            current_depth_cm=float(data.get("current_depth_cm", 5.0)),
            biomass_g_m2=float(data.get("biomass_g_m2", 0.0)),
            layer_fractions=list(fracs) if fracs else None,
        )


@dataclass(frozen=True)
class RootFluxes:
    depth_inc_cm: float
    biomass_delta_g_m2: float
