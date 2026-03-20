from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BiomassPools:
    leaf_g_m2: float = 0.0
    stem_g_m2: float = 0.0
    root_g_m2: float = 0.0
    grain_g_m2: float = 0.0


@dataclass(frozen=True)
class BiomassAllocations:
    leaf_g_m2: float
    stem_g_m2: float
    root_g_m2: float
    grain_g_m2: float
