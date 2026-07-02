"""Immutable soil aggregation parameters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SoilAggregationParams:
    """Parameters governing aggregate formation and breakdown.

    Three-class model: micro (<0.02 mm), meso (0.02–0.25 mm), macro (>0.25 mm).

    Attributes:
        macro_formation_rate_per_week: Base rate of micro/meso → macro formation
            under optimal root/fungal activity. Ref: Six et al. 2004, Table 3.
        meso_formation_rate_per_week: Base rate of micro → meso formation
            from clay flocculation and organic binding.
        root_formation_weight: Contribution of root density to macro formation.
            Ref: Tisdall & Oades 1982 — root enmeshment of particles.
        fungal_formation_weight: Contribution of fungal hyphae to macro formation.
            Ref: Tisdall & Oades 1982 — glomalin and hyphal binding.
        tillage_macro_destruction_min: Minimum fraction of macroaggregates destroyed
            by tillage at intensity=1.0. Ref: Six et al. 2000, SSSAJ.
        tillage_macro_destruction_max: Maximum fraction destroyed.
        wet_dry_macro_breakdown: Fraction of macroaggregates broken per wet-dry
            cycle. Ref: Denef et al. 2001, Soil Biol Biochem.
        freeze_thaw_macro_breakdown: Fraction broken per freeze-thaw cycle.
            Ref: Six et al. 2004 — 10–20% per cycle in temperate soils.
        raindrop_surface_breakdown: Fraction of surface macro broken per day
            per mm of rainfall above threshold.
            Ref: Le Bissonnais 1996, Catena.
        rain_threshold_mm: Daily rainfall above which raindrop impact matters.
        freeze_temp_c: Temperature threshold for freeze detection.
        temp_min_c: Minimum temperature for biological formation (cardinal).
        temp_optimum_c: Optimal temperature for formation (cardinal).
        temp_max_c: Lethal high temperature — formation ceases.
            Ref: enzyme denaturation above ~40°C.
        plow_depth_cm: Maximum tillage depth at intensity=1.0 (moldboard plow).
            The plow zone spans 0 to ``plow_depth_cm × intensity``;
            ``AggregationModule.apply_tillage`` pro-rates per-layer destruction
            by the fraction of each layer's thickness inside that zone, matching
            ``BioporeModule.apply_tillage`` (#215). Ref: DSSAT — typical plow
            depth 20–30 cm.
    """

    macro_formation_rate_per_week: float = 0.015
    meso_formation_rate_per_week: float = 0.010
    root_formation_weight: float = 0.6
    fungal_formation_weight: float = 0.4
    tillage_macro_destruction_min: float = 0.30
    tillage_macro_destruction_max: float = 0.70
    wet_dry_macro_breakdown: float = 0.10
    freeze_thaw_macro_breakdown: float = 0.15
    raindrop_surface_breakdown: float = 0.002
    rain_threshold_mm: float = 10.0
    freeze_temp_c: float = 0.0
    temp_min_c: float = 2.0
    temp_optimum_c: float = 25.0
    temp_max_c: float = 42.0
    plow_depth_cm: float = 30.0
