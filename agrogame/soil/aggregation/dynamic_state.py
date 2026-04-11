"""Dynamic soil layer properties derived from aggregation state."""

from __future__ import annotations


def effective_ksat_factor(macro_frac: float) -> float:
    """Scale ksat based on macroaggregate fraction.

    Well-aggregated soil has large interconnected pores from macro-
    aggregates, increasing hydraulic conductivity 2–5x over degraded soil.

    Ref: Dexter 2004, Geoderma — soil physical quality; ksat correlates
         with macroporosity which scales with macroaggregate content.

    Args:
        macro_frac: Macroaggregate fraction (0–1).

    Returns:
        Multiplier on base ksat (0.5–2.5 range).
    """
    # Linear from 0.5 at macro=0 to 2.5 at macro=1
    return 0.5 + 2.0 * max(0.0, min(1.0, macro_frac))


def effective_porosity(base_saturation: float, macro_frac: float) -> float:
    """Adjust porosity based on aggregation state.

    Well-aggregated: 45–55% porosity (inter-aggregate macropores).
    Degraded: 35–40% (compacted, few macropores).

    Ref: Bronick & Lal 2005, Geoderma — soil structure and management.

    Args:
        base_saturation: Static porosity from soil profile (≈ saturation).
        macro_frac: Macroaggregate fraction (0–1).

    Returns:
        Adjusted porosity (clamped to physical bounds).
    """
    # Shift range: -0.027 (macro=0) to +0.08 (macro=1) around base.
    # At macro=0.25 (default tilled) → no shift; below → decrease; above → increase
    shift = 0.08 * (macro_frac - 0.25) / 0.75
    adjusted = base_saturation + shift
    return max(0.30, min(0.60, adjusted))


def root_penetration_factor(mwd_mm: float) -> float:
    """Root penetration resistance factor based on MWD.

    Well-aggregated soil (high MWD) has lower mechanical resistance,
    allowing faster root elongation.

    Ref: Dexter 2004, Geoderma — S-index and root penetration;
         Bengough et al. 2011, J Exp Bot — root elongation vs strength.

    Args:
        mwd_mm: Mean weight diameter (mm).

    Returns:
        Multiplier on root elongation rate (0.3–1.0).
    """
    if mwd_mm <= 0.0:
        return 0.3
    # Sigmoid-like: 0.3 at MWD=0, ~0.7 at MWD=0.5, ~0.95 at MWD=1.5, 1.0 at MWD≥2.0
    factor = 0.3 + 0.7 * min(1.0, mwd_mm / 2.0)
    return min(1.0, factor)


def som_protection_factor(
    base_frac: float,
    clay_pct: float,
    mwd_mm: float,
    clay_scale: float = 40.0,
    protection_reduction: float = 0.70,
) -> float:
    """Protection factor combining clay and aggregate MWD.

    Clay provides chemical protection (mineral-organic complexes).
    Aggregation provides physical protection (occluded C inaccessible
    to decomposers).

    Ref: Six et al. 2002, Plant Soil — aggregate turnover and SOM;
         Tisdall & Oades 1982 — aggregate hierarchy.

    Args:
        base_frac: Base protected fraction (pool-specific).
        clay_pct: Clay content (%).
        mwd_mm: Mean weight diameter (mm).
        clay_scale: Clay % at which clay protection is 100%.
        protection_reduction: Max rate reduction for protected C.

    Returns:
        Multiplier in [1 - protection_reduction, 1.0] where lower = more protected.
    """
    # Clay component (original)
    clay_component = min(1.0, max(0.0, clay_pct) / clay_scale)
    # MWD component: well-aggregated soil physically protects SOM
    # Scale: 0 at MWD=0, 1.0 at MWD≥2.0
    mwd_component = min(1.0, max(0.0, mwd_mm) / 2.0)
    # Combined: average of clay and MWD protection (both contribute)
    combined = 0.5 * clay_component + 0.5 * mwd_component
    protected = base_frac * combined
    return 1.0 - protected * protection_reduction
