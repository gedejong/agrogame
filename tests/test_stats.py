from __future__ import annotations

import math
import pytest

from agrogame.analysis.stats import (
    rmse,
    mae,
    mbe,
    r2,
    nse,
    willmott_d,
    coverage_within,
    align_series,
    phenology_timing_error_days,
)


def test_basic_metrics_perfect_match():
    obs = [1.0, 2.0, 3.0]
    sim = [1.0, 2.0, 3.0]
    assert rmse(obs, sim) == 0.0
    assert mae(obs, sim) == 0.0
    assert mbe(obs, sim) == 0.0
    assert r2(obs, sim) == pytest.approx(1.0, abs=1e-12)
    assert nse(obs, sim) == 1.0
    assert willmott_d(obs, sim) == 1.0
    assert coverage_within(obs, sim, tol=0.0) == 1.0


def test_basic_metrics_simple_offsets():
    obs = [1.0, 2.0, 3.0]
    sim = [2.0, 3.0, 4.0]
    # Deterministic expectations
    assert rmse(obs, sim) == 1.0
    assert mae(obs, sim) == 1.0
    assert mbe(obs, sim) == 1.0
    assert r2(obs, sim) == pytest.approx(
        1.0, abs=1e-12
    )  # perfect correlation with offset
    assert nse(obs, sim) == -0.5  # worse than mean predictor by factor 1.5
    assert willmott_d(obs, sim) > 0.0
    assert coverage_within(obs, sim, tol=1.0) == 1.0


def test_align_series_and_phenology_error():
    xs = ["2020-01-01", "2020-01-02", "2020-01-03"]
    xv = [1.0, 2.0, 3.0]
    ys = ["2020-01-02", "2020-01-03", "2020-01-04"]
    yv = [2.0, 3.5, 4.0]
    ao, asv = align_series(xs, ys, xv, yv)
    assert ao == [2.0, 3.0]
    assert asv == [2.0, 3.5]
    # Phenology timing error simple average
    assert phenology_timing_error_days([0, 10, 20], [0, 12, 18]) == (0 + 2 + 2) / 3


def test_edge_cases_and_errors():
    # Mismatched lengths -> error
    with pytest.raises(ValueError):
        rmse([1, 2], [1])

    # Constant perfect match cases
    obs = [2.0, 2.0, 2.0]
    sim = [2.0, 2.0, 2.0]
    assert r2(obs, sim) == 1.0
    assert nse(obs, sim) == 1.0
    assert willmott_d(obs, sim) == 1.0

    # Constant observed, different simulation -> edge paths
    obs = [1.0, 1.0, 1.0]
    sim = [2.0, 2.0, 2.0]
    nse_val = nse(obs, sim)
    assert math.isinf(nse_val) and nse_val < 0
    # Willmott d defined but less than 1
    assert 0.0 <= willmott_d(obs, sim) < 1.0

    # Coverage calculation
    assert coverage_within([0, 0.4, 1.2], [0.1, 0.3, 1.0], tol=0.2) == 1.0
