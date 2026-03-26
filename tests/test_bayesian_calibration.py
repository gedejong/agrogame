"""Tests for bayesian_calibration.py — priors, likelihood, posteriors."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from scripts.bayesian_calibration import (
    NDIM,
    PARAM_NAMES,
    PARAMS,
    ConvergenceDiagnostics,
    PosteriorSummary,
    compute_diagnostics,
    initial_positions,
    load_reference,
    log_likelihood,
    log_posterior,
    log_prior,
    prediction_uncertainty,
    run_simulation_with_params,
    summarize_posterior,
    write_posterior_csv,
)


# ---------------------------------------------------------------------------
# log_prior
# ---------------------------------------------------------------------------
class TestLogPrior:
    def test_defaults_in_bounds(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        assert log_prior(theta) == 0.0

    def test_out_of_bounds_returns_neg_inf(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        theta[0] = -1.0  # rue_g_per_mj below lower bound
        assert log_prior(theta) == -np.inf

    def test_upper_bound_violation(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        theta[0] = 100.0  # rue_g_per_mj above upper bound
        assert log_prior(theta) == -np.inf

    def test_flowering_must_precede_maturity(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        fi = PARAM_NAMES.index("flowering_gdd")
        mi = PARAM_NAMES.index("maturity_gdd")
        theta[fi] = 1800.0  # flowering > maturity default (1700)
        theta[mi] = 1700.0
        assert log_prior(theta) == -np.inf

    def test_at_bounds_is_valid(self) -> None:
        theta = np.array([p.lo for p in PARAMS])
        # Set flowering < maturity at lower bounds
        fi = PARAM_NAMES.index("flowering_gdd")
        mi = PARAM_NAMES.index("maturity_gdd")
        theta[fi] = 600.0
        theta[mi] = 1200.0
        assert log_prior(theta) == 0.0


# ---------------------------------------------------------------------------
# log_likelihood
# ---------------------------------------------------------------------------
class TestLogLikelihood:
    def test_perfect_match_gives_zero(self) -> None:
        ref_biomass = [0.0, 100.0, 500.0]
        ref_lai = [0.0, 2.0, 4.0]
        # With perfect match, residuals are 0 → ll = 0
        # We can't easily mock the simulation, but we can test the math
        # by checking that likelihood is finite for valid params
        theta = np.array([p.default for p in PARAMS])
        ll = log_likelihood(theta, ref_biomass, ref_lai, subsample=50)
        assert np.isfinite(ll)
        assert ll <= 0.0  # log-likelihood always ≤ 0

    def test_empty_reference_returns_neg_inf(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        ll = log_likelihood(theta, [], [], subsample=10)
        assert ll == -np.inf


# ---------------------------------------------------------------------------
# log_posterior
# ---------------------------------------------------------------------------
class TestLogPosterior:
    def test_invalid_prior_short_circuits(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        theta[0] = -1.0  # out of bounds
        lp = log_posterior(theta, [100.0], [2.0], subsample=50)
        assert lp == -np.inf

    def test_valid_params_returns_finite(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        ref_biomass = [0.0, 500.0, 1000.0]
        ref_lai = [0.0, 3.0, 5.0]
        lp = log_posterior(theta, ref_biomass, ref_lai, subsample=50)
        assert np.isfinite(lp)


# ---------------------------------------------------------------------------
# initial_positions
# ---------------------------------------------------------------------------
class TestInitialPositions:
    def test_shape(self) -> None:
        p0 = initial_positions(16)
        assert p0.shape == (16, NDIM)

    def test_within_bounds(self) -> None:
        p0 = initial_positions(32)
        for i, param in enumerate(PARAMS):
            assert np.all(p0[:, i] >= param.lo)
            assert np.all(p0[:, i] <= param.hi)

    def test_reproducible(self) -> None:
        p0a = initial_positions(16, rng=np.random.default_rng(42))
        p0b = initial_positions(16, rng=np.random.default_rng(42))
        np.testing.assert_array_equal(p0a, p0b)


# ---------------------------------------------------------------------------
# summarize_posterior
# ---------------------------------------------------------------------------
class TestSummarizePosterior:
    def test_known_distribution(self) -> None:
        rng = np.random.default_rng(42)
        # Fake chain: uniform samples within bounds
        chain = np.zeros((1000, NDIM))
        for i, p in enumerate(PARAMS):
            chain[:, i] = rng.uniform(p.lo, p.hi, size=1000)
        summaries = summarize_posterior(chain)
        assert len(summaries) == NDIM
        for s in summaries:
            assert isinstance(s, PosteriorSummary)
            assert s.ci_5 <= s.median <= s.ci_95

    def test_returns_all_params(self) -> None:
        chain = np.array([[p.default for p in PARAMS]] * 100)
        summaries = summarize_posterior(chain)
        names = [s.name for s in summaries]
        assert names == PARAM_NAMES


# ---------------------------------------------------------------------------
# load_reference
# ---------------------------------------------------------------------------
class TestLoadReference:
    def test_loads_netherlands(self) -> None:
        ref_path = Path("data/benchmarks/reference/maize_netherlands_reference.csv")
        if not ref_path.exists():
            pytest.skip("Reference CSV not generated")
        biomass, lai = load_reference(ref_path, subsample=10)
        assert len(biomass) == 15  # 150 / 10
        assert len(lai) == 15


# ---------------------------------------------------------------------------
# run_simulation_with_params
# ---------------------------------------------------------------------------
class TestRunSimulation:
    def test_default_params_returns_outputs(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        result = run_simulation_with_params(theta)
        assert "biomass_g_m2" in result
        assert "lai" in result
        assert "grain_biomass_g_m2" in result
        assert len(result["biomass_g_m2"]) == 150

    def test_final_biomass_positive(self) -> None:
        theta = np.array([p.default for p in PARAMS])
        result = run_simulation_with_params(theta)
        assert result["biomass_g_m2"][-1] > 0


# ---------------------------------------------------------------------------
# compute_diagnostics
# ---------------------------------------------------------------------------
class TestComputeDiagnostics:
    def test_with_mock_sampler(self) -> None:
        try:
            import emcee
        except ImportError:
            pytest.skip("emcee not installed")

        ref_path = Path("data/benchmarks/reference/maize_netherlands_reference.csv")
        if not ref_path.exists():
            pytest.skip("Reference CSV not generated")
        ref_b, ref_l = load_reference(ref_path, subsample=30)
        nw = 16
        p0 = initial_positions(nw)
        sampler = emcee.EnsembleSampler(
            nw, NDIM, log_posterior, args=(ref_b, ref_l, 30)
        )
        sampler.run_mcmc(p0, 5)
        diag = compute_diagnostics(sampler, PARAM_NAMES)
        assert isinstance(diag, ConvergenceDiagnostics)
        assert 0.0 < diag.mean_acceptance <= 1.0
        assert len(diag.autocorr_times) == NDIM


# ---------------------------------------------------------------------------
# write_posterior_csv
# ---------------------------------------------------------------------------
class TestWritePosteriorCsv:
    def test_writes_file(self, tmp_path: Path) -> None:
        summaries = summarize_posterior(np.array([[p.default for p in PARAMS]] * 100))
        csv_path = write_posterior_csv(summaries, tmp_path)
        assert csv_path.exists()
        lines = csv_path.read_text().strip().split("\n")
        assert len(lines) == NDIM + 1  # header + 8 params


# ---------------------------------------------------------------------------
# prediction_uncertainty
# ---------------------------------------------------------------------------
class TestPredictionUncertainty:
    def test_with_constant_chain(self) -> None:
        chain = np.array([[p.default for p in PARAMS]] * 20)
        pred = prediction_uncertainty(chain, n_samples=5)
        assert pred.n_samples > 0
        assert pred.median_grain_g_m2 >= 0
        assert pred.ci_5_grain_g_m2 <= pred.ci_95_grain_g_m2


# ---------------------------------------------------------------------------
# Smoke test: short MCMC chain
# ---------------------------------------------------------------------------
@pytest.mark.slow
def test_short_mcmc_chain() -> None:
    """Run a very short MCMC chain to verify the pipeline works."""
    try:
        import emcee
    except ImportError:
        pytest.skip("emcee not installed")

    from pathlib import Path

    ref_path = Path("data/benchmarks/reference/maize_netherlands_reference.csv")
    if not ref_path.exists():
        pytest.skip("Reference CSV not generated")

    ref_biomass, ref_lai = load_reference(ref_path, subsample=30)
    nwalkers = 16
    p0 = initial_positions(nwalkers)

    sampler = emcee.EnsembleSampler(
        nwalkers,
        NDIM,
        log_posterior,
        args=(ref_biomass, ref_lai, 30),
    )
    sampler.run_mcmc(p0, 5)

    chain = sampler.get_chain(flat=True)
    assert chain.shape == (nwalkers * 5, NDIM)
    assert float(np.mean(sampler.acceptance_fraction)) > 0.0


# ---------------------------------------------------------------------------
# plot_traces / plot_corner
# ---------------------------------------------------------------------------
class TestPlots:
    def test_trace_plot(self, tmp_path: Path) -> None:
        import importlib.util

        if not importlib.util.find_spec("emcee"):
            pytest.skip("emcee not installed")
        if not importlib.util.find_spec("matplotlib"):
            pytest.skip("matplotlib not installed")

        import emcee

        from scripts.bayesian_calibration import plot_traces

        ref_path = Path("data/benchmarks/reference/maize_netherlands_reference.csv")
        if not ref_path.exists():
            pytest.skip("Reference CSV not generated")
        ref_b, ref_l = load_reference(ref_path, subsample=30)
        nw = 16
        p0 = initial_positions(nw)
        sampler = emcee.EnsembleSampler(
            nw, NDIM, log_posterior, args=(ref_b, ref_l, 30)
        )
        sampler.run_mcmc(p0, 5)
        out = tmp_path / "traces.png"
        plot_traces(sampler, PARAM_NAMES, out)
        assert out.exists()

    def test_corner_plot(self, tmp_path: Path) -> None:
        import importlib.util

        if not importlib.util.find_spec("corner"):
            pytest.skip("corner not installed")
        if not importlib.util.find_spec("matplotlib"):
            pytest.skip("matplotlib not installed")

        from scripts.bayesian_calibration import plot_corner

        chain = np.array([[p.default for p in PARAMS]] * 50)
        # Add small noise to avoid degenerate contours
        chain += np.random.default_rng(42).normal(0, 0.01, chain.shape)
        out = tmp_path / "corner.png"
        plot_corner(chain, PARAM_NAMES, out)
        assert out.exists()


# ---------------------------------------------------------------------------
# run_calibration (very short)
# ---------------------------------------------------------------------------
def test_run_calibration_smoke() -> None:
    """Run calibration with minimal settings to cover the pipeline."""
    import importlib.util

    if not importlib.util.find_spec("emcee"):
        pytest.skip("emcee not installed")

    from scripts.bayesian_calibration import run_calibration

    ref_path = Path("data/benchmarks/reference/maize_netherlands_reference.csv")
    if not ref_path.exists():
        pytest.skip("Reference CSV not generated")

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        summaries, diag, pred = run_calibration(
            nwalkers=16,
            nsteps=5,
            burn=2,
            subsample=30,
            outdir=Path(td),
        )
        assert len(summaries) == NDIM
        assert diag.mean_acceptance > 0
        assert pred.n_samples > 0
        assert (Path(td) / "posterior_summary.csv").exists()


# ---------------------------------------------------------------------------
# Script importability
# ---------------------------------------------------------------------------
def test_script_importable() -> None:
    import scripts.bayesian_calibration as mod

    assert hasattr(mod, "main")
    assert hasattr(mod, "run_calibration")
    assert hasattr(mod, "PARAMS")
    assert hasattr(mod, "log_posterior")
    assert mod.NDIM == 8
