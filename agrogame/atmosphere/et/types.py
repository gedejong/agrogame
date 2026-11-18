from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EtComponents:
    potential_evap_mm: float
    potential_transp_mm: float
    et0_mm: float


@dataclass
class EtState:
    """Mutable ET state tracking cumulative soil-evap (used by Ritchie stage logic)."""

    # Stage-2 soil evaporation depends on the time since the last wetting
    # (Ritchie 1972, Water Resour. Res. 8:1204-1213), so the cumulative
    # evaporation since wetting is state, carried across days and saved with
    # the patch (ETRuntime memory, #577); it is not a per-day cache.
    cumulative_evap_mm: float = 0.0


@dataclass
class ResidueState:
    """Surface-residue state: cover fraction and decay half-life."""

    cover_fraction: float = 0.0
    decay_half_life_days: float = 0.0  # 0 = no decay


@dataclass(frozen=True)
class EtActual:
    evaporation_mm: float
    transpiration_mm: float
    canopy_evap_mm: float = 0.0
