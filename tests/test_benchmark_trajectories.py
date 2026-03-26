"""Tests for benchmark_trajectories.py — Taylor stats, timing, and GYGA comparison."""

from __future__ import annotations

import pytest

from scripts.benchmark_trajectories import (
    TaylorStats,
    find_peak_day,
    gyga_compare,
    load_reference_csv,
    pearson_r,
    std_dev,
    taylor_stats,
)


# ---------------------------------------------------------------------------
# pearson_r
# ---------------------------------------------------------------------------
class TestPearsonR:
    def test_perfect_positive(self) -> None:
        assert pearson_r([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)

    def test_perfect_negative(self) -> None:
        assert pearson_r([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)

    def test_zero_variance(self) -> None:
        assert pearson_r([5, 5, 5], [1, 2, 3]) == 0.0

    def test_known_value(self) -> None:
        # x=[1,2,3], y=[1,3,2] → r = 0.5
        r = pearson_r([1, 2, 3], [1, 3, 2])
        assert r == pytest.approx(0.5, abs=0.01)

    def test_single_element(self) -> None:
        assert pearson_r([1.0], [2.0]) == 0.0


# ---------------------------------------------------------------------------
# std_dev
# ---------------------------------------------------------------------------
class TestStdDev:
    def test_constant(self) -> None:
        assert std_dev([7.0, 7.0, 7.0]) == 0.0

    def test_known(self) -> None:
        # Population std of [2, 4, 4, 4, 5, 5, 7, 9] = 2.0
        assert std_dev([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.0, abs=0.01)

    def test_single_element(self) -> None:
        assert std_dev([42.0]) == 0.0


# ---------------------------------------------------------------------------
# taylor_stats
# ---------------------------------------------------------------------------
class TestTaylorStats:
    def test_identical_series(self) -> None:
        ref = [1.0, 2.0, 3.0, 4.0, 5.0]
        ts = taylor_stats(ref, ref, variable="test")
        assert ts.correlation == pytest.approx(1.0)
        assert ts.std_ratio == pytest.approx(1.0)
        assert ts.crmsd == pytest.approx(0.0, abs=1e-10)

    def test_scaled_series(self) -> None:
        ref = [1.0, 2.0, 3.0, 4.0, 5.0]
        sim = [2.0, 4.0, 6.0, 8.0, 10.0]  # 2x
        ts = taylor_stats(ref, sim)
        assert ts.correlation == pytest.approx(1.0)
        assert ts.std_ratio == pytest.approx(2.0)

    def test_shifted_series(self) -> None:
        ref = [1.0, 2.0, 3.0, 4.0, 5.0]
        sim = [11.0, 12.0, 13.0, 14.0, 15.0]  # +10
        ts = taylor_stats(ref, sim)
        assert ts.correlation == pytest.approx(1.0)
        assert ts.std_ratio == pytest.approx(1.0)
        # CRMSD should be 0 (centred removes bias)
        assert ts.crmsd == pytest.approx(0.0, abs=1e-10)

    def test_returns_dataclass(self) -> None:
        ts = taylor_stats([1, 2, 3], [3, 2, 1], variable="lai", scenario="test")
        assert isinstance(ts, TaylorStats)
        assert ts.variable == "lai"
        assert ts.scenario == "test"

    def test_crmsd_law_of_cosines(self) -> None:
        """CRMSD² = 1 + ratio² - 2*ratio*r (normalised Taylor identity)."""
        ref = [1.0, 3.0, 2.0, 5.0, 4.0]
        sim = [1.5, 2.5, 3.0, 4.0, 3.5]
        ts = taylor_stats(ref, sim)
        expected_crmsd2 = 1.0 + ts.std_ratio**2 - 2.0 * ts.std_ratio * ts.correlation
        assert ts.crmsd**2 == pytest.approx(expected_crmsd2, abs=1e-6)


# ---------------------------------------------------------------------------
# find_peak_day
# ---------------------------------------------------------------------------
class TestFindPeakDay:
    def test_simple(self) -> None:
        assert find_peak_day([0, 1, 5, 3, 2]) == 2

    def test_peak_at_end(self) -> None:
        assert find_peak_day([1, 2, 3]) == 2

    def test_empty(self) -> None:
        assert find_peak_day([]) == 0


# ---------------------------------------------------------------------------
# gyga_compare
# ---------------------------------------------------------------------------
class TestGygaCompare:
    def test_within_range(self) -> None:
        gc = gyga_compare("maize", "netherlands_temperate", "test", 800.0)
        # 800 g/m² grain * 0.01 = 8 t/ha; GYGA = 11 t/ha; ratio = 0.73
        assert gc.sim_yield_t_ha == pytest.approx(8.0)
        assert gc.status == "within range"

    def test_overestimation(self) -> None:
        gc = gyga_compare("maize", "kenya_highlands", "test", 1200.0)
        # 12 t/ha vs 7 t/ha → ratio 1.71 → overestimation
        assert gc.status == "overestimation"

    def test_underestimation(self) -> None:
        gc = gyga_compare("maize", "sahel_arid", "test", 50.0)
        # 0.5 t/ha vs 3 t/ha → ratio 0.17 → underestimation
        assert gc.status == "underestimation"

    def test_unknown_crop(self) -> None:
        gc = gyga_compare("millet", "sahel_arid", "test", 500.0)
        assert gc.gyga_yield_t_ha == 0.0
        assert gc.ratio == 0.0


# ---------------------------------------------------------------------------
# load_reference_csv
# ---------------------------------------------------------------------------
class TestLoadReferenceCsv:
    def test_loads_netherlands(self) -> None:
        from pathlib import Path

        ref_path = Path("data/benchmarks/reference/maize_netherlands_reference.csv")
        if not ref_path.exists():
            pytest.skip("Reference CSV not generated")
        data = load_reference_csv(ref_path)
        assert "lai" in data
        assert "biomass_g_m2" in data
        assert len(data["day"]) == 150

    def test_loads_all_columns(self) -> None:
        from pathlib import Path

        ref_path = Path("data/benchmarks/reference/maize_kenya_reference.csv")
        if not ref_path.exists():
            pytest.skip("Reference CSV not generated")
        data = load_reference_csv(ref_path)
        expected_cols = {
            "day",
            "lai",
            "biomass_g_m2",
            "cumulative_et_mm",
            "soil_moisture_top30_mm",
        }
        assert expected_cols == set(data.keys())


# ---------------------------------------------------------------------------
# Script smoke test (importability)
# ---------------------------------------------------------------------------
def test_script_importable() -> None:
    """Verify the benchmark script can be imported without side effects."""
    import scripts.benchmark_trajectories as mod

    assert hasattr(mod, "main")
    assert hasattr(mod, "taylor_stats")
    assert hasattr(mod, "GYGA_YIELDS")
    assert hasattr(mod, "SCENARIOS")
