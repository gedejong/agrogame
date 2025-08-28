from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtParams:
    method: str = "priestley-taylor"
    pt_alpha: float = 1.26
    extinction_coefficient_k: float = 0.6
    stage1_limit_mm: float = 6.0
    ritchie_coef: float = 3.5
