from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CanopyState:
    """Mutable canopy state: LAI, biomass partitioning, last computed water stress."""

    lai: float
    biomass_g_m2: float
    stem_biomass_g_m2: float = 0.0
    grain_biomass_g_m2: float = 0.0
    last_water_stress: float = 1.0  # 1=no stress, 0=severe (supply/demand)
    # Emergent potential grain number (grains m^-2) set during the
    # peri-anthesis critical window by the sink-source model (#321). Zero
    # under the legacy fixed-HI path. Kernel weight = grain / grain_number.
    grain_number: float = 0.0
    # Grain-fill progress (#515). Accumulated GDD at the grain-fill
    # transition (anchors the senescence ramp and the grain-set window),
    # shoot biomass at that transition (the #321 lag-phase baseline), and
    # whether the grain-set window has closed. Kept here rather than on
    # CanopyModule so a mid-season save carries them.
    grain_fill_start_gdd: float = 0.0
    lag_start_biomass_g_m2: float = 0.0
    grain_number_frozen: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "lai": self.lai,
            "biomass_g_m2": self.biomass_g_m2,
            "stem_biomass_g_m2": self.stem_biomass_g_m2,
            "grain_biomass_g_m2": self.grain_biomass_g_m2,
            "last_water_stress": self.last_water_stress,
            "grain_number": self.grain_number,
            "grain_fill_start_gdd": self.grain_fill_start_gdd,
            "lag_start_biomass_g_m2": self.lag_start_biomass_g_m2,
            "grain_number_frozen": self.grain_number_frozen,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CanopyState:
        return cls(
            lai=float(data.get("lai", 0.0)),
            biomass_g_m2=float(data.get("biomass_g_m2", 0.0)),
            stem_biomass_g_m2=float(data.get("stem_biomass_g_m2", 0.0)),
            grain_biomass_g_m2=float(data.get("grain_biomass_g_m2", 0.0)),
            last_water_stress=float(data.get("last_water_stress", 1.0)),
            grain_number=float(data.get("grain_number", 0.0)),
            # Optional within schema v1 (#515): pre-#515 saves default to the
            # pre-grain-fill values.
            grain_fill_start_gdd=float(data.get("grain_fill_start_gdd", 0.0)),
            lag_start_biomass_g_m2=float(data.get("lag_start_biomass_g_m2", 0.0)),
            grain_number_frozen=bool(data.get("grain_number_frozen", False)),
        )


@dataclass
class CanopyFluxes:
    intercepted_par_mj_m2: float
    biomass_increment_g_m2: float  # shoot share of the daily assimilate pool
    # Below-ground share of the same finite pool, partitioned to roots (#337).
    # biomass_increment_g_m2 + root_increment_g_m2 = the day's total assimilate.
    root_increment_g_m2: float = 0.0
