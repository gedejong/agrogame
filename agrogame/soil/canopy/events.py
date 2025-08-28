from __future__ import annotations

from dataclasses import dataclass
from agrogame.events import BaseEvent


@dataclass(frozen=True)
class LightIntercepted(BaseEvent):
    fraction: float
    incident_par_mj_m2: float
    intercepted_par_mj_m2: float


@dataclass(frozen=True)
class BiomassAccumulated(BaseEvent):
    increment_g_m2: float
    total_g_m2: float


@dataclass(frozen=True)
class LAIUpdated(BaseEvent):
    previous_lai: float
    new_lai: float
