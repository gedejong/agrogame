from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtComponents:
    potential_evap_mm: float
    potential_transp_mm: float
    et0_mm: float


@dataclass
class EtState:
    cumulative_evap_mm: float = 0.0


@dataclass
class ResidueState:
    cover_fraction: float = 0.0
    decay_half_life_days: float = 0.0  # 0 = no decay


@dataclass(frozen=True)
class EtActual:
    evaporation_mm: float
    transpiration_mm: float
    canopy_evap_mm: float = 0.0
