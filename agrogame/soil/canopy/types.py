from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CanopyState:
    lai: float
    biomass_g_m2: float
    stem_biomass_g_m2: float = 0.0
    grain_biomass_g_m2: float = 0.0
    last_water_stress: float = 1.0  # 1=no stress, 0=severe (supply/demand)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lai": self.lai,
            "biomass_g_m2": self.biomass_g_m2,
            "stem_biomass_g_m2": self.stem_biomass_g_m2,
            "grain_biomass_g_m2": self.grain_biomass_g_m2,
            "last_water_stress": self.last_water_stress,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanopyState:
        return cls(
            lai=float(data.get("lai", 0.0)),
            biomass_g_m2=float(data.get("biomass_g_m2", 0.0)),
            stem_biomass_g_m2=float(data.get("stem_biomass_g_m2", 0.0)),
            grain_biomass_g_m2=float(data.get("grain_biomass_g_m2", 0.0)),
            last_water_stress=float(data.get("last_water_stress", 1.0)),
        )


@dataclass
class CanopyFluxes:
    intercepted_par_mj_m2: float
    biomass_increment_g_m2: float
