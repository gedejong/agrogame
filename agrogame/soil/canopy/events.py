from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LightIntercepted:
    fraction: float
    incident_par_mj_m2: float
    intercepted_par_mj_m2: float


@dataclass(frozen=True)
class BiomassAccumulated:
    increment_g_m2: float
    total_g_m2: float


@dataclass(frozen=True)
class LAIUpdated:
    previous_lai: float
    new_lai: float
