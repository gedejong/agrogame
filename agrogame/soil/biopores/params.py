"""Immutable biopore parameters (#215)."""

from __future__ import annotations

from dataclasses import dataclass, fields


def _check_unit_interval(name: str, value: float) -> None:
    """Raise if value is outside [0, 1]."""
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


def _check_positive(name: str, value: float) -> None:
    """Raise if value is not strictly > 0."""
    if value <= 0.0:
        raise ValueError(f"{name} must be > 0")


def _check_non_negative(name: str, value: float) -> None:
    """Raise if value is < 0."""
    if value < 0.0:
        raise ValueError(f"{name} must be >= 0")


# Field name → validator. Driven by dataclass field order so adding a field
# requires only one extra entry here.
_VALIDATORS = {
    "structural_root_fraction": _check_unit_interval,
    "conversion_factor": _check_unit_interval,
    "decay_half_life_days_topsoil": _check_positive,
    "decay_half_life_days_subsoil": _check_positive,
    "topsoil_depth_cm": _check_non_negative,
    "max_density_per_m2": _check_non_negative,
    "plow_depth_cm": _check_non_negative,
    "tillage_destruction_max_frac": _check_unit_interval,
    "compaction_sensitivity": _check_unit_interval,
    "mean_radius_mm": _check_positive,
    "root_density_g_per_cm3": _check_positive,
}


@dataclass(frozen=True)
class BioporeParams:
    """Parameters governing biopore creation, decay, and destruction.

    Biopores are persistent cylindrical macropores left behind by root
    channels (Kautz 2015) — and, in future #76, by earthworm burrows.
    They enhance preferential flow, root penetration, and gas exchange.

    Defaults calibrated against Pierret et al. 2007's structured-soil
    biopore density range (50–500 /m²) — see ADR-009 for the calibration
    decisions and sensitivity sweep behind each value.

    Attributes:
        structural_root_fraction: Fraction of dead-root mass that is
            *structural* (>~0.5 mm dia) — only this fraction leaves
            persistent channels. Fine roots decompose without
            durable channel imprints. Ref: Six et al. 2004; Kautz
            2015 §2 — typically 0.1–0.3.
        conversion_factor: Fraction of *structural* dead-root volume
            that converts to persistent biopore volume. Defaults to
            1.0 because the structural fraction (above) already
            captures the not-all-mass-becomes-channel reality;
            ``conversion_factor`` then represents the cylindrical
            channel literally carved by the structural root. Tuneable
            in [0, 1] for sensitivity studies.
        decay_half_life_days_topsoil: Half-life of biopore density in
            the topsoil layer. Active biology recolonises and faunal
            soil mixing collapses channels. Ref: Kautz 2015 — 60-180
            days; we use the upper bound so the calibrated steady-state
            depth profile stays physical (topsoil ≥ subsoil density,
            per Pierret 2007). See ADR-009.
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
        mean_radius_mm: Default biopore radius (mm). Pierret 2007
            channel diameters mostly 0.5-2 mm; Kautz 2015 cereal
            channels 1-3 mm. We default to 1.0 mm — at the lower
            cereal bound — because the 2.0 mm default produced
            density two orders of magnitude below Pierret's range
            (#290 calibration).
        root_density_g_per_cm3: Bulk density of dead root tissue used
            to convert mass to volume (g/cm³). Ref: Bidlack & Buxton
            1992 — typical fine-root density 0.6-1.0 g/cm³.
    """

    structural_root_fraction: float = 0.2
    conversion_factor: float = 1.0
    decay_half_life_days_topsoil: float = 180.0
    decay_half_life_days_subsoil: float = 365.0
    topsoil_depth_cm: float = 30.0
    max_density_per_m2: float = 500.0
    plow_depth_cm: float = 30.0
    tillage_destruction_max_frac: float = 0.7
    compaction_sensitivity: float = 0.4
    mean_radius_mm: float = 1.0
    root_density_g_per_cm3: float = 0.8

    def __post_init__(self) -> None:
        """Validate params at construction time (frozen-dataclass pattern)."""
        for f in fields(self):
            validator = _VALIDATORS.get(f.name)
            if validator is not None:
                validator(f.name, getattr(self, f.name))
