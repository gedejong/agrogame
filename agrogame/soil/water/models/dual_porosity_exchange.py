"""First-order macropore-matrix water exchange.

Pure function, kept separate for testability. Implements the
Gerke & van Genuchten (1993) first-order linear exchange between
macropore and matrix domains at daily timestep.

Physical interpretation: macropore water (transient, gravity-held)
diffuses into the surrounding matrix at a rate proportional to the
macropore storage and limited by matrix available pore space. Matrix
water can reverse-flow into macropores only at saturation (expulsion).

The driver is a normalized saturation gradient:
    driver = (theta_macro / macro_frac) - (theta_matrix / saturation)

On a common 0-1 scale, this captures the physical sense of
Gerke & van Genuchten Eq. 7 without being thrown off by the
absolute scale difference between domains.

Refs:
    Gerke, H.H. & van Genuchten, M.Th. 1993. A dual-porosity model
    for simulating the preferential movement of water and solutes in
    structured porous media. Water Resour. Res. 29(2): 305-319. Eq. 7.
"""

from __future__ import annotations

from typing import List

from agrogame.soil.models import SoilProfile

_EPS = 1e-9


def compute_exchange_mm(
    theta_macro: List[float],
    theta_matrix: List[float],
    profile: SoilProfile,
    alpha_w_per_day: float,
    macro_frac: List[float],
) -> List[float]:
    """Per-layer macropore-to-matrix exchange (mm/day).

    Positive return value = macro → matrix (macropore water diffusing
    into matrix). Negative = matrix → macro (saturation expulsion; rare).

    Magnitude is capped bidirectionally: cannot transfer more than the
    source domain holds, and cannot overfill the sink domain.

    Args:
        theta_macro: Macropore volumetric water content per layer
            (m3/m3 of bulk soil). Must satisfy 0 <= theta_macro <= macro_frac.
        theta_matrix: Matrix volumetric water content per layer (m3/m3).
        profile: Soil profile (for layer depths and saturation bounds).
        alpha_w_per_day: First-order exchange coefficient (1/day).
        macro_frac: Macropore volume fraction per layer from
            ``PoreNetworkState.macro`` (m3/m3).

    Returns:
        Per-layer exchange amount in mm. List length = min of inputs.
    """
    n = min(len(theta_macro), len(theta_matrix), len(profile.layers), len(macro_frac))
    out: List[float] = []
    for i in range(n):
        layer = profile.layers[i]
        depth_mm = layer.depth_cm * 10.0

        # Normalized saturation in each domain (0..1).
        macro_rel = theta_macro[i] / macro_frac[i] if macro_frac[i] > _EPS else 0.0
        matrix_rel = (
            theta_matrix[i] / layer.saturation if layer.saturation > _EPS else 0.0
        )
        driver = macro_rel - matrix_rel
        # Gerke & van Genuchten Eq. 7 with normalized saturations.
        raw_mm = alpha_w_per_day * driver * depth_mm

        macro_stored_mm = theta_macro[i] * depth_mm
        matrix_room_mm = max(0.0, (layer.saturation - theta_matrix[i]) * depth_mm)

        if raw_mm > 0.0:
            # Macro → matrix. Cap by source stored and sink room.
            q_ex = min(raw_mm, macro_stored_mm, matrix_room_mm)
        else:
            # Matrix → macro (rare). Cap by matrix-above-wp and macro-room.
            matrix_above_wp_mm = max(
                0.0, (theta_matrix[i] - layer.wilting_point) * depth_mm
            )
            macro_room_mm = max(0.0, (macro_frac[i] - theta_macro[i]) * depth_mm)
            q_ex = -min(-raw_mm, matrix_above_wp_mm, macro_room_mm)
        out.append(q_ex)
    return out
