from __future__ import annotations


def cn_to_S_mm(cn: int) -> float:
    return max(0.0, (25400.0 / cn) - 254.0)


def scs_runoff_mm(precip_mm: float, cn: int) -> float:
    S = cn_to_S_mm(cn)
    Ia = 0.2 * S
    if precip_mm <= Ia:
        return 0.0
    return ((precip_mm - Ia) ** 2) / (precip_mm - Ia + S)
