"""Immutable biopore parameters (#215)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BioporeParams:
    """Parameters governing biopore creation, decay, and destruction.

    Biopores are persistent cylindrical macropores left behind by root
    channels (Kautz 2015) — and, in future #76, by earthworm burrows.
    They enhance preferential flow, root penetration, and gas exchange.

    Attributes:
        conversion_factor: Fraction of dead-root volume that converts
            to persistent biopore volume per layer. Thicker roots
            leave more durable channels (Six et al. 2004 — 0.3-0.8).
        decay_half_life_days_topsoil: Half-life of biopore density in
            the topsoil layer. Active biology recolonises faster.
            Ref: Kautz 2015 — 60-180 days.
        decay_half_life_days_subsoil: Subsoil half-life. Lower biology
            and slower mass-flow → longer persistence (180-730 days).
        topsoil_depth_cm: Boundary used to switch between topsoil and
            subsoil decay rates.
        max_density_per_m2: Cap on biopore count per m². Reflects
            physical accommodation limits (Pierret et al. 2007 ≤500).
        plow_depth_cm: Tillage destruction reaches this depth.
            Matches AggregationParams default.
        tillage_destruction_max_frac: Fraction of biopores destroyed
            in plow-depth layers at intensity=1.0. Ref: Shipitalo &
            Butt 1999 — moldboard 60-80%.
        compaction_sensitivity: Fraction destroyed per unit
            (intensity × moisture_factor) under wheel traffic.
        mean_radius_mm: Default biopore radius (mm). 1-3 mm typical
            for cereal roots; 2 mm midpoint.
        root_density_g_per_cm3: Bulk density of dead root tissue used
            to convert mass to volume (g/cm³). Ref: Bidlack & Buxton
            1992 — typical fine-root density 0.6-1.0 g/cm³.
    """

    conversion_factor: float = 0.5
    decay_half_life_days_topsoil: float = 90.0
    decay_half_life_days_subsoil: float = 365.0
    topsoil_depth_cm: float = 30.0
    max_density_per_m2: float = 500.0
    plow_depth_cm: float = 30.0
    tillage_destruction_max_frac: float = 0.7
    compaction_sensitivity: float = 0.4
    mean_radius_mm: float = 2.0
    root_density_g_per_cm3: float = 0.8
