"""SCS Curve Number helper functions.

Implements the USDA SCS runoff curve number method to estimate surface runoff
from rainfall.
"""

from __future__ import annotations


def cn_to_S_mm(cn: int) -> float:
    """Convert curve number to potential maximum retention S (mm).

    Args:
        cn: Curve number (dimensionless), typically 30–100.

    Returns:
        Potential maximum retention S in mm.
    """
    return max(0.0, (25400.0 / cn) - 254.0)


def scs_runoff_mm(precip_mm: float, cn: int) -> float:
    """Compute runoff depth (mm) using SCS CN method.

    Args:
        precip_mm: Precipitation depth (mm).
        cn: Curve number.

    Returns:
        Runoff depth (mm).
    """
    S = cn_to_S_mm(cn)
    Ia = 0.2 * S
    if precip_mm <= Ia:
        return 0.0
    return ((precip_mm - Ia) ** 2) / (precip_mm - Ia + S)
