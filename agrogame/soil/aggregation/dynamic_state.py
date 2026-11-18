"""Dynamic soil layer properties derived from aggregation state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from agrogame.soil.aggregation.state import SoilAggregationState

if TYPE_CHECKING:
    from agrogame.soil.pore_network.state import PoreNetworkState

# Physical bounds on total porosity for mineral agricultural soils.
_POROSITY_MIN = 0.30
_POROSITY_MAX = 0.60


def effective_ksat_factor(macro_frac: float) -> float:
    """Scale ksat based on macroaggregate fraction.

    Well-aggregated soil has large interconnected pores from macro-
    aggregates, increasing hydraulic conductivity 2–5x over degraded soil.

    Ref: Dexter 2004, Geoderma — soil physical quality; ksat correlates
         with macroporosity which scales with macroaggregate content.

    The water balance uses only ``min(1, factor)``: the cascading bucket's
    daily share of above-field-capacity water drained, so a factor above 1
    has no effect there, and ``ksat_mm_per_hour`` is not read by the water
    balance at all. The API's ``ksat_mm_day`` (base Ksat × this factor) is a
    reported structural index (#524).

    Args:
        macro_frac: Macroaggregate fraction (0–1).

    Returns:
        Multiplier on base ksat (0.5–2.5 range).
    """
    # Linear from 0.5 at macro=0 to 2.5 at macro=1
    return 0.5 + 2.0 * max(0.0, min(1.0, macro_frac))


def effective_porosity(
    base_saturation: float,
    macro_frac: float,
    pore_state: PoreNetworkState | None = None,
    layer: int | None = None,
) -> float:
    """Effective (drainable) porosity for the daily water balance.

    Two derivations, selected by whether a detailed pore breakdown is
    supplied (#289):

    **Detailed (preferred, when ``pore_state`` and ``layer`` are given).**
    Delegates to the pore-network module's retention-curve partition and
    returns the *effective* porosity excluding residual water — total
    porosity minus the cryptopore (<0.2 um) fraction, which holds water so
    tightly it is never drained nor plant-available. This equals macro +
    meso + micro, i.e. ``total_porosity(layer) - crypto[layer]``, or
    equivalently φ − θ_r. (Note this is the air-capacity/effective
    porosity, not the *strict* drainable porosity / specific yield
    θ_sat − θ_fc, which would exclude retained plant-available water too.)

    Ref: Luxmoore 1981, SSSAJ — pore-size classes (cryptopores <0.2 um are
         residual/bound water); Rawls et al. 1982, Trans. ASAE — theta_r.

    Note: the detailed value is **invariant to aggregation state**.
    This is a direct consequence of how the model is structured, not a
    deliberate cancellation: ``total_porosity`` is pinned to the *static*
    ``layer.saturation`` and cryptoporosity is texture-only, so
    ``total - crypto`` reduces to ``saturation - residual(clay)`` and
    carries no structural term at all. The mean-weight-diameter shift only
    reshuffles macro vs coarse-meso *within* this pool. Delegating
    therefore drops the aggregation->porosity feedback that the ad-hoc
    scalar fallback below applied to the water balance. That is a net
    improvement, not a double-counting fix: aggregation and porosity are
    *distinct* real effects, but total porosity being static here means the
    pore breakdown genuinely carries no aggregation signal. Aggregation
    reaches the water balance only through ``effective_ksat_factor``, which
    the cascading bucket applies as ``min(1, factor)`` to the daily share of
    above-field-capacity water drained, so a factor above 1 has no effect.
    The aggregation-driven macro/meso split and connectivity feed no
    simulated flux (ADR-016, #524). Biopore donation draws on crypto first,
    so it raises this value by at most the biopore volume fraction (0.0016
    at 500 /m²). That binds only when a layer saturates, moving θ by at
    most half as much (<= 7.9e-4 m³/m³ at 500 /m², ADR-010 #524 amendment),
    since the bucket retains at most half the excess. The old scalar
    shift was a crude heuristic with ~zero dynamical effect, so removing it
    loses no load-bearing physics; see the #289 PR for the measured
    magnitude of the shift.

    **Scalar fallback (backward-compatible, when no ``pore_state``).**
    Approximates porosity by shifting static saturation with the
    macroaggregate fraction: well-aggregated 45-55% (inter-aggregate
    macropores), degraded 35-40% (compacted).

    Ref: Bronick & Lal 2005, Geoderma — soil structure and management.

    Args:
        base_saturation: Static porosity from soil profile (≈ saturation).
        macro_frac: Macroaggregate fraction (0–1); scalar path only.
        pore_state: Optional detailed pore-size distribution. When given
            together with ``layer``, the detailed derivation is used.
        layer: Layer index into ``pore_state``; required for the detailed
            path.

    Returns:
        Effective porosity (clamped to physical bounds).
    """
    if pore_state is not None and layer is not None and layer < len(pore_state.macro):
        # Drainable porosity: exclude the tightly bound cryptopore water.
        detailed = pore_state.total_porosity(layer) - pore_state.crypto[layer]
        return max(_POROSITY_MIN, min(_POROSITY_MAX, detailed))

    # Shift range: -0.027 (macro=0) to +0.08 (macro=1) around base.
    # At macro=0.25 (default tilled) → no shift; below → decrease; above → increase
    shift = 0.08 * (macro_frac - 0.25) / 0.75
    adjusted = base_saturation + shift
    return max(_POROSITY_MIN, min(_POROSITY_MAX, adjusted))


def root_penetration_factor(mwd_mm: float) -> float:
    """Root penetration resistance factor based on MWD.

    Well-aggregated soil (high MWD) has lower mechanical resistance,
    allowing faster root elongation.

    Ref: Dexter 2004, Geoderma — S-index and root penetration;
         Bengough et al. 2011, J Exp Bot — root elongation vs strength.

    The simulation no longer reads this against the evolving aggregate
    state. It is evaluated once, at the default initial structure, to give
    :data:`CALIBRATED_ROOT_ELONGATION_FACTOR` (ADR-021, #526).

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


# Constant multiplier on root elongation (ADR-021, #526). It is
# ``root_penetration_factor`` at the MWD of the default initial structure
# (``SoilAggregationState.from_layers``: 0.55125 mm, giving 0.4929375), the
# value every crop's root front ran under on day 0 when the realism suite was
# calibrated. It preserves that calibration and is not a soil-strength
# parameter. Root elongation used to read the topsoil MWD each day, so a
# moldboard pass, which destroys macroaggregates, slowed rooting by 21-31 %
# and cost up to 30 % of season-2 grain (#526). Tillage must not tighten
# rooting: it lowers plough-layer bulk density (Lampurlanés &
# Cantero-Martínez 2003, Agron. J. 95:526-536, doi:10.2134/agronj2003.5260),
# and zero tillage raises surface bulk density and penetration resistance
# (Grant & Lafond 1993, Can. J. Soil Sci. 73:223-232, doi:10.4141/cjss93-024),
# yet root growth differs little between tillage systems. The CERES-Maize and
# APSIM root fronts have no aggregate-structure or tillage term either.
# The engine and the forecast (``agrogame/api/routes.py``) share this one
# definition. See docs/adr/ADR-021-root-elongation-aggregate-coupling.md.
CALIBRATED_ROOT_ELONGATION_FACTOR: float = root_penetration_factor(
    SoilAggregationState.from_layers(1).mwd(0)
)


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
