from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple


def _to_lists(
    obs: Iterable[float], sim: Iterable[float]
) -> Tuple[List[float], List[float]]:
    o = list(obs)
    s = list(sim)
    if len(o) != len(s) or len(o) == 0:
        raise ValueError("obs and sim must be same non-zero length")
    return o, s


def rmse(obs: Iterable[float], sim: Iterable[float]) -> float:
    o, s = _to_lists(obs, sim)
    n = len(o)
    return (sum((si - oi) ** 2 for oi, si in zip(o, s)) / n) ** 0.5


def mae(obs: Iterable[float], sim: Iterable[float]) -> float:
    o, s = _to_lists(obs, sim)
    n = len(o)
    return sum(abs(si - oi) for oi, si in zip(o, s)) / n


def mbe(obs: Iterable[float], sim: Iterable[float]) -> float:
    o, s = _to_lists(obs, sim)
    n = len(o)
    return sum((si - oi) for oi, si in zip(o, s)) / n


def r2(obs: Iterable[float], sim: Iterable[float]) -> float:
    """Coefficient of determination as squared Pearson correlation (r^2).

    This returns 1.0 for perfect linear relationships with any intercept.
    """
    o, s = _to_lists(obs, sim)
    n = len(o)
    o_mean = sum(o) / n
    s_mean = sum(s) / n
    cov = sum((oi - o_mean) * (si - s_mean) for oi, si in zip(o, s))
    var_o = sum((oi - o_mean) ** 2 for oi in o)
    var_s = sum((si - s_mean) ** 2 for si in s)
    if var_o == 0.0 or var_s == 0.0:
        # If both are constant and equal → perfect; otherwise undefined → 0.0
        return (
            1.0
            if all(oi == s[0] for oi in o) and var_o == 0.0 and var_s == 0.0
            else 0.0
        )
    r = cov / (var_o**0.5 * var_s**0.5)
    return float(r * r)


def nse(obs: Iterable[float], sim: Iterable[float]) -> float:
    """Nash–Sutcliffe efficiency."""
    o, s = _to_lists(obs, sim)
    o_mean = sum(o) / len(o)
    numerator = sum((si - oi) ** 2 for oi, si in zip(o, s))
    denominator = sum((oi - o_mean) ** 2 for oi in o)
    if denominator == 0.0:
        return 1.0 if numerator == 0.0 else -float("inf")
    return 1.0 - numerator / denominator


def willmott_d(obs: Iterable[float], sim: Iterable[float]) -> float:
    """Willmott's index of agreement (d)."""
    o, s = _to_lists(obs, sim)
    o_mean = sum(o) / len(o)
    num = sum((si - oi) ** 2 for oi, si in zip(o, s))
    den = sum((abs(si - o_mean) + abs(oi - o_mean)) ** 2 for oi, si in zip(o, s))
    if den == 0.0:
        return 1.0 if num == 0.0 else 0.0
    return 1.0 - num / den


def coverage_within(obs: Iterable[float], sim: Iterable[float], tol: float) -> float:
    """Fraction of pairs with |sim-obs| <= tol."""
    o, s = _to_lists(obs, sim)
    count = sum(1 for oi, si in zip(o, s) if abs(si - oi) <= tol)
    return count / len(o)


def align_series(
    xs: Sequence, ys: Sequence, xv: Sequence[float], yv: Sequence[float]
) -> Tuple[List[float], List[float]]:
    """Align two series by key sequences xs, ys and values xv, yv.

    Returns values for keys present in both.
    """
    if len(xs) != len(xv) or len(ys) != len(yv):
        raise ValueError("keys and values must be same length for each series")
    xmap = dict(zip(xs, xv))
    ymap = dict(zip(ys, yv))
    common = [k for k in xs if k in ymap]
    return [xmap[k] for k in common], [ymap[k] for k in common]


def phenology_timing_error_days(
    obs_days: Iterable[int], sim_days: Iterable[int]
) -> float:
    """Mean absolute error in days between observed and simulated stage dates."""
    return mae(obs_days, sim_days)
