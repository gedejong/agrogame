from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtParams:
    method: str = "priestley-taylor"  # or "penman-monteith"
    # Priestley–Taylor
    pt_alpha: float = 1.26
    # Partitioning / canopy
    extinction_coefficient_k: float = 0.6
    # Ritchie soil evaporation
    stage1_limit_mm: float = 6.0
    ritchie_coef: float = 3.5
    # Penman–Monteith (FAO-56 style) + stomatal response
    pm_use_fao56: bool = True
    pm_canopy_height_m: float = 0.6
    rs_min_s_m: float = 70.0  # reference surface resistance (s/m)
    vpd_ref_kpa: float = 1.0
    vpd_sensitivity: float = 0.15  # linear reduction per kPa above ref
    # Residue/mulch evaporation reduction (DSSAT-style linear)
    residue_cover_fraction: float = 0.0  # 0-1 surface coverage
    residue_stage1_reduction: float = 0.6  # max fractional reduction at full cover
    residue_stage2_reduction: float = 0.4  # max fractional reduction at full cover
    wetting_reset_threshold_mm: float = 10.0  # rainfall that resets to Stage 1
