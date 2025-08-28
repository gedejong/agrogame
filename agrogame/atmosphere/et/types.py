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


@dataclass(frozen=True)
class EtActual:
    evaporation_mm: float
    transpiration_mm: float
