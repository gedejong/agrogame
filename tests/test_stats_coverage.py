"""Tests covering missing lines in agrogame/analysis/stats.py."""

from __future__ import annotations

import pytest

from agrogame.analysis.stats import align_series, r2


# ---------------------------------------------------------------------------
# align_series with use_union=True and sort_keys (lines 111-117)
# ---------------------------------------------------------------------------


def test_align_series_union_and_sort() -> None:
    """Cover lines 111-117: use_union=True with sort_keys=True."""
    xs = ["a", "b", "c"]
    xv = [1.0, 2.0, 3.0]
    ys = ["b", "c", "d"]
    yv = [20.0, 30.0, 40.0]
    ao, asv = align_series(xs, ys, xv, yv, use_union=True, sort_keys=True)
    # Only keys in both: b, c
    assert ao == [2.0, 3.0]
    assert asv == [20.0, 30.0]


def test_align_series_union_without_sort() -> None:
    """Cover line 112: use_union=True without sort_keys."""
    xs = ["a", "b"]
    xv = [1.0, 2.0]
    ys = ["b", "c"]
    yv = [20.0, 30.0]
    ao, asv = align_series(xs, ys, xv, yv, use_union=True, sort_keys=False)
    # Only key "b" is in both
    assert len(ao) == 1
    assert ao[0] == 2.0


def test_align_series_intersection_sorted() -> None:
    """Cover line 119: intersection with sort_keys=True."""
    xs = ["c", "a", "b"]
    xv = [3.0, 1.0, 2.0]
    ys = ["b", "a"]
    yv = [20.0, 10.0]
    ao, asv = align_series(xs, ys, xv, yv, sort_keys=True)
    assert ao == [1.0, 2.0]  # sorted: a, b
    assert asv == [10.0, 20.0]


# ---------------------------------------------------------------------------
# align_series mismatched length error (line 107)
# ---------------------------------------------------------------------------


def test_align_series_mismatched_keys_values() -> None:
    """Cover line 107: keys and values length mismatch."""
    with pytest.raises(ValueError, match="keys and values must be same length"):
        align_series(["a", "b"], ["c", "d"], [1.0], [3.0, 4.0])


# ---------------------------------------------------------------------------
# r2 edge cases: one constant, one varying (line 107 guard in r2)
# ---------------------------------------------------------------------------


def test_r2_obs_constant_sim_varying() -> None:
    """Cover line 107 in r2: var_o==0 but var_s!=0 -> returns 0."""
    val = r2([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])
    assert val == 0.0


def test_r2_sim_constant_obs_varying() -> None:
    """Cover var_s==0, var_o!=0 -> returns 0."""
    val = r2([1.0, 2.0, 3.0], [5.0, 5.0, 5.0])
    assert val == 0.0
