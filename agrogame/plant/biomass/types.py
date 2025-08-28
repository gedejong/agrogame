from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BiomassPools:
    leaf_g_m2: float = 0.0
    stem_g_m2: float = 0.0
    root_g_m2: float = 0.0
    grain_g_m2: float = 0.0


@dataclass
class BiomassAllocations:
    leaf_g_m2: float
    stem_g_m2: float
    root_g_m2: float
    grain_g_m2: float


@dataclass(frozen=True)
class StressFactors:
    water: float = 1.0  # 0..1, lower means drought
    nitrogen: float = 1.0  # 0..1, lower means N stress
