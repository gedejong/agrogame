#!/usr/bin/env python3
"""Bayesian parameter calibration for AgroGame using MCMC (emcee).

Calibrates 8 high-priority parameters (identified by AGRO-90 Morris screening)
against DSSAT/APSIM reference trajectories (from AGRO-91) using an affine-invariant
ensemble sampler.

Usage:
    poetry run python scripts/bayesian_calibration.py [options]

    # Quick smoke run (for testing):
    poetry run python scripts/bayesian_calibration.py --steps 20 --walkers 16 --burn 10

References:
    Foreman-Mackey, D. et al. (2013) emcee: The MCMC Hammer.
        Publ. Astron. Soc. Pacific, 125(925):306-312.
    Vrugt, J.A. (2016) Markov chain Monte Carlo simulation using the DREAM
        software package. Environ. Model. Softw., 75:273-316.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Parameter definitions: 8 priority params from AGRO-90 sensitivity analysis
# Uniform priors bounded by literature ranges.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CalibrationParam:
    """One parameter to calibrate with its prior bounds."""

    name: str
    lo: float
    hi: float
    default: float
    group: str  # canopy, phenology, et


PARAMS: list[CalibrationParam] = [
    CalibrationParam("rue_g_per_mj", 1.5, 4.5, 3.0, "canopy"),
    CalibrationParam("temp_opt_c", 22.0, 36.0, 30.0, "canopy"),
    CalibrationParam("pt_alpha", 1.0, 1.5, 1.26, "et"),
    CalibrationParam("extinction_coefficient_k", 0.40, 0.80, 0.65, "canopy"),
    CalibrationParam("flowering_gdd", 600.0, 1200.0, 900.0, "phenology"),
    CalibrationParam("maturity_gdd", 1200.0, 2200.0, 1700.0, "phenology"),
    CalibrationParam("sla_m2_per_g", 0.012, 0.030, 0.02, "canopy"),
    CalibrationParam("remobilization_fraction", 0.0, 0.05, 0.02, "canopy"),
]

PARAM_NAMES: list[str] = [p.name for p in PARAMS]
NDIM: int = len(PARAMS)

# Observation noise (assumed std dev for each variable)
SIGMA_BIOMASS: float = 80.0  # g/m² — typical field measurement error
SIGMA_LAI: float = 0.5  # m²/m² — typical LAI-2200 measurement error


# ---------------------------------------------------------------------------
# Prior, likelihood, posterior
# ---------------------------------------------------------------------------
def log_prior(theta: np.ndarray) -> float:
    """Uniform prior: 0 if all params within bounds, -inf otherwise."""
    for i, p in enumerate(PARAMS):
        if not (p.lo <= theta[i] <= p.hi):
            return -np.inf
    # Constraint: flowering_gdd < maturity_gdd
    flowering_idx = PARAM_NAMES.index("flowering_gdd")
    maturity_idx = PARAM_NAMES.index("maturity_gdd")
    if theta[flowering_idx] >= theta[maturity_idx]:
        return -np.inf
    return 0.0


def run_simulation_with_params(
    theta: np.ndarray,
    crop_name: str = "maize",
    climate_name: str = "netherlands_temperate",
    start: date | None = None,
    days: int = 150,
    seed: int = 42,
) -> dict[str, list[float]]:
    """Run simulation with given parameter vector, return daily outputs."""
    if start is None:
        start = date(2024, 4, 1)
    from agrogame.atmosphere.et import EtParams
    from agrogame.plant.presets import CropPreset, load_crop_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.loader import load_soil_presets
    from agrogame.soil.phenology import GrowthStageThresholds
    from agrogame.soil.water.types import DailyDrivers
    from agrogame.weather.generator import SyntheticWeatherGenerator
    from agrogame.weather.presets import load_climate_presets

    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    base_crop = crops.get_preset(crop_name, climate_name)
    climate = climates.climates[climate_name]

    vals = {PARAM_NAMES[i]: float(theta[i]) for i in range(NDIM)}

    canopy = replace(
        base_crop.canopy,
        radiation_use_efficiency_g_per_mj=vals["rue_g_per_mj"],
        temp_opt_c=vals["temp_opt_c"],
        extinction_coefficient_k=vals["extinction_coefficient_k"],
        specific_leaf_area_m2_per_g=vals["sla_m2_per_g"],
        remobilization_fraction=vals["remobilization_fraction"],
    )
    phenology = replace(
        base_crop.phenology,
        thresholds=GrowthStageThresholds(
            emergence_gdd=base_crop.phenology.thresholds.emergence_gdd,
            flowering_gdd=vals["flowering_gdd"],
            maturity_gdd=vals["maturity_gdd"],
        ),
    )
    et_params = EtParams(pt_alpha=vals["pt_alpha"])

    crop = CropPreset(
        name=base_crop.name,
        phenology=phenology,
        canopy=canopy,
        roots=base_crop.roots,
    )

    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, start)
    orch = FullSimulationOrchestrator(
        profile,
        crop=crop,
        latitude_deg=climate.latitude_deg,
        et_params=et_params,
    )

    result: dict[str, list[float]] = {
        "biomass_g_m2": [],
        "lai": [],
        "grain_biomass_g_m2": [],
    }
    for rec in series.records:
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
        result["biomass_g_m2"].append(orch.canopy.state.biomass_g_m2)
        result["lai"].append(orch.canopy.state.lai)
        result["grain_biomass_g_m2"].append(orch.canopy.state.grain_biomass_g_m2)
    return result


def load_reference(path: Path, subsample: int = 10) -> tuple[list[float], list[float]]:
    """Load reference biomass and LAI, subsampled every N days."""
    columns: dict[str, list[float]] = {}
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key, val in row.items():
                columns.setdefault(key, []).append(float(val))
    biomass = columns.get("biomass_g_m2", [])
    lai = columns.get("lai", [])
    return biomass[::subsample], lai[::subsample]


def log_likelihood(
    theta: np.ndarray,
    ref_biomass: Sequence[float],
    ref_lai: Sequence[float],
    subsample: int = 10,
    crop_name: str = "maize",
    climate_name: str = "netherlands_temperate",
) -> float:
    """Gaussian log-likelihood against reference trajectories.

    Compares subsampled biomass and LAI trajectories.
    """
    try:
        sim = run_simulation_with_params(
            theta, crop_name=crop_name, climate_name=climate_name
        )
    except (ValueError, RuntimeError, ZeroDivisionError):
        return -np.inf

    sim_biomass = sim["biomass_g_m2"][::subsample]
    sim_lai = sim["lai"][::subsample]

    n_b = min(len(ref_biomass), len(sim_biomass))
    n_l = min(len(ref_lai), len(sim_lai))

    if n_b == 0 and n_l == 0:
        return -np.inf

    ll = 0.0
    for i in range(n_b):
        diff = sim_biomass[i] - ref_biomass[i]
        ll -= 0.5 * (diff / SIGMA_BIOMASS) ** 2
    for i in range(n_l):
        diff = sim_lai[i] - ref_lai[i]
        ll -= 0.5 * (diff / SIGMA_LAI) ** 2
    return ll


def log_posterior(
    theta: np.ndarray,
    ref_biomass: Sequence[float],
    ref_lai: Sequence[float],
    subsample: int = 10,
    crop_name: str = "maize",
    climate_name: str = "netherlands_temperate",
) -> float:
    """Log-posterior = log-prior + log-likelihood."""
    lp = log_prior(theta)
    if not np.isfinite(lp):
        return -np.inf
    return lp + log_likelihood(
        theta, ref_biomass, ref_lai, subsample, crop_name, climate_name
    )


# ---------------------------------------------------------------------------
# Initial walker positions
# ---------------------------------------------------------------------------
def initial_positions(
    nwalkers: int, rng: np.random.Generator | None = None
) -> np.ndarray:
    """Generate initial walker positions near parameter defaults."""
    if rng is None:
        rng = np.random.default_rng(42)
    p0 = np.zeros((nwalkers, NDIM))
    for i, param in enumerate(PARAMS):
        spread = 0.1 * (param.hi - param.lo)
        lo = max(param.lo, param.default - spread)
        hi = min(param.hi, param.default + spread)
        p0[:, i] = rng.uniform(lo, hi, size=nwalkers)
    return p0


# ---------------------------------------------------------------------------
# Convergence diagnostics
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ConvergenceDiagnostics:
    """Summary of MCMC chain convergence."""

    mean_acceptance: float
    autocorr_times: dict[str, float]
    converged: bool


def compute_diagnostics(sampler: Any, param_names: list[str]) -> ConvergenceDiagnostics:
    """Compute acceptance fraction and autocorrelation times."""
    mean_acc = float(np.mean(sampler.acceptance_fraction))
    autocorr: dict[str, float] = {}
    try:
        tau = sampler.get_autocorr_time(quiet=True)
        for i, name in enumerate(param_names):
            autocorr[name] = float(tau[i])
    except (ValueError, RuntimeError, ZeroDivisionError):
        for name in param_names:
            autocorr[name] = float("nan")

    converged = mean_acc > 0.15 and all(np.isfinite(v) for v in autocorr.values())
    return ConvergenceDiagnostics(
        mean_acceptance=mean_acc,
        autocorr_times=autocorr,
        converged=converged,
    )


# ---------------------------------------------------------------------------
# Posterior summary
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PosteriorSummary:
    """Summary statistics for one parameter's posterior."""

    name: str
    median: float
    ci_5: float
    ci_95: float
    prior_lo: float
    prior_hi: float
    default: float


def summarize_posterior(
    flat_chain: np.ndarray,
) -> list[PosteriorSummary]:
    """Compute posterior medians and 90% credible intervals."""
    summaries: list[PosteriorSummary] = []
    for i, param in enumerate(PARAMS):
        samples = flat_chain[:, i]
        median = float(np.median(samples))
        ci_5 = float(np.percentile(samples, 5))
        ci_95 = float(np.percentile(samples, 95))
        summaries.append(
            PosteriorSummary(
                name=param.name,
                median=median,
                ci_5=ci_5,
                ci_95=ci_95,
                prior_lo=param.lo,
                prior_hi=param.hi,
                default=param.default,
            )
        )
    return summaries


# ---------------------------------------------------------------------------
# Prediction uncertainty
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PredictionUncertainty:
    """Yield prediction with uncertainty from posterior samples."""

    median_grain_g_m2: float
    ci_5_grain_g_m2: float
    ci_95_grain_g_m2: float
    n_samples: int


def prediction_uncertainty(
    flat_chain: np.ndarray,
    n_samples: int = 100,
    rng: np.random.Generator | None = None,
    crop_name: str = "maize",
    climate_name: str = "netherlands_temperate",
) -> PredictionUncertainty:
    """Run forward simulations from posterior samples for yield CI."""
    if rng is None:
        rng = np.random.default_rng(99)
    n_total = flat_chain.shape[0]
    indices = rng.choice(n_total, size=min(n_samples, n_total), replace=False)

    grain_yields: list[float] = []
    for idx in indices:
        theta = flat_chain[idx]
        try:
            sim = run_simulation_with_params(
                theta, crop_name=crop_name, climate_name=climate_name
            )
            grain = sim["grain_biomass_g_m2"][-1] if sim["grain_biomass_g_m2"] else 0.0
            grain_yields.append(grain)
        except (ValueError, RuntimeError, ZeroDivisionError):
            continue

    if not grain_yields:
        return PredictionUncertainty(0.0, 0.0, 0.0, 0)

    arr = np.array(grain_yields)
    return PredictionUncertainty(
        median_grain_g_m2=float(np.median(arr)),
        ci_5_grain_g_m2=float(np.percentile(arr, 5)),
        ci_95_grain_g_m2=float(np.percentile(arr, 95)),
        n_samples=len(grain_yields),
    )


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------
def plot_traces(
    sampler: Any,
    param_names: list[str],
    output_path: Path,
) -> None:
    """Plot MCMC trace plots for each parameter."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping trace plots")
        return

    chain = sampler.get_chain()
    ndim = len(param_names)
    fig, axes = plt.subplots(ndim, 1, figsize=(10, 2 * ndim), sharex=True)
    if ndim == 1:
        axes = [axes]
    for i, ax in enumerate(axes):
        ax.plot(chain[:, :, i], alpha=0.3, linewidth=0.5)
        ax.set_ylabel(param_names[i], fontsize=8)
        ax.axhline(PARAMS[i].default, color="k", ls="--", lw=0.8)
    axes[-1].set_xlabel("Step")
    fig.suptitle("MCMC Trace Plots", fontsize=12)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)
    print(f"  Trace plot: {output_path}")


def plot_corner(
    flat_chain: np.ndarray,
    param_names: list[str],
    output_path: Path,
) -> None:
    """Plot corner plot (posterior distributions)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import corner as corner_pkg
    except ImportError:
        print("corner/matplotlib not available — skipping corner plot")
        return

    defaults = [p.default for p in PARAMS]
    fig = corner_pkg.corner(
        flat_chain,
        labels=param_names,
        truths=defaults,
        quantiles=[0.05, 0.5, 0.95],
        show_titles=True,
        title_fmt=".3f",
    )
    fig.savefig(str(output_path), dpi=150)
    import matplotlib.pyplot as plt

    plt.close(fig)
    print(f"  Corner plot: {output_path}")


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------
def write_posterior_csv(summaries: list[PosteriorSummary], outdir: Path) -> Path:
    """Write posterior summary table to CSV."""
    path = outdir / "posterior_summary.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "parameter",
                "median",
                "ci_5",
                "ci_95",
                "prior_lo",
                "prior_hi",
                "default",
            ]
        )
        for s in summaries:
            writer.writerow(
                [
                    s.name,
                    f"{s.median:.4f}",
                    f"{s.ci_5:.4f}",
                    f"{s.ci_95:.4f}",
                    f"{s.prior_lo:.4f}",
                    f"{s.prior_hi:.4f}",
                    f"{s.default:.4f}",
                ]
            )
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_calibration(
    nwalkers: int = 32,
    nsteps: int = 500,
    burn: int = 200,
    subsample: int = 10,
    outdir: Path | None = None,
    crop_name: str = "maize",
    climate_name: str = "netherlands_temperate",
    reference_path: Path | None = None,
) -> tuple[list[PosteriorSummary], ConvergenceDiagnostics, PredictionUncertainty]:
    """Run the full MCMC calibration pipeline."""
    import emcee

    if outdir is None:
        outdir = Path("out/calibration")

    outdir.mkdir(parents=True, exist_ok=True)

    # Load reference data
    if reference_path is None:
        ref_dir = Path("data/benchmarks/reference")
        # Try common naming patterns
        candidates = [
            ref_dir / f"{crop_name}_{climate_name}_reference.csv",
            ref_dir / f"{crop_name}_{climate_name.split('_')[0]}_reference.csv",
        ]
        reference_path = next((c for c in candidates if c.exists()), candidates[0])
    if not reference_path.exists():
        print(f"ERROR: reference not found: {reference_path}")
        sys.exit(1)
    ref_biomass, ref_lai = load_reference(reference_path, subsample=subsample)
    print(
        f"Calibrating {crop_name} x {climate_name} "
        f"({len(ref_biomass)} biomass + {len(ref_lai)} LAI points)"
    )

    # Initialize sampler
    p0 = initial_positions(nwalkers)
    sampler = emcee.EnsembleSampler(
        nwalkers,
        NDIM,
        log_posterior,
        args=(ref_biomass, ref_lai, subsample, crop_name, climate_name),
    )

    # Run MCMC
    total_steps = burn + nsteps
    print(
        f"Running MCMC: {nwalkers} walkers x {total_steps} steps "
        f"({burn} burn-in + {nsteps} production)"
    )
    sampler.run_mcmc(p0, total_steps, progress=True)

    # Diagnostics
    diag = compute_diagnostics(sampler, PARAM_NAMES)
    print(f"\nAcceptance fraction: {diag.mean_acceptance:.3f}")
    print("Autocorrelation times:")
    for name, tau in diag.autocorr_times.items():
        print(f"  {name}: {tau:.1f}")

    # Discard burn-in and flatten
    flat_chain = sampler.get_chain(discard=burn, flat=True)
    print(f"Posterior samples: {flat_chain.shape[0]}")

    # Posterior summary
    summaries = summarize_posterior(flat_chain)
    print(f"\n{'Parameter':<28} {'Median':>10} {'90% CI':>20} {'Default':>10}")
    print(f"{'-'*28} {'-'*10} {'-'*20} {'-'*10}")
    for s in summaries:
        ci_str = f"[{s.ci_5:.3f}, {s.ci_95:.3f}]"
        print(f"{s.name:<28} {s.median:>10.4f} {ci_str:>20} {s.default:>10.4f}")

    # Prediction uncertainty
    print("\nComputing prediction uncertainty (posterior predictive)...")
    pred = prediction_uncertainty(
        flat_chain, n_samples=100, crop_name=crop_name, climate_name=climate_name
    )
    print(
        f"Netherlands maize grain yield = "
        f"{pred.median_grain_g_m2:.0f} g/m² "
        f"(90% CI: [{pred.ci_5_grain_g_m2:.0f}, "
        f"{pred.ci_95_grain_g_m2:.0f}] g/m²)"
    )
    yield_t_ha = pred.median_grain_g_m2 * 0.01
    ci5_t_ha = pred.ci_5_grain_g_m2 * 0.01
    ci95_t_ha = pred.ci_95_grain_g_m2 * 0.01
    print(
        f"  = {yield_t_ha:.2f} t/ha "
        f"(90% CI: [{ci5_t_ha:.2f}, {ci95_t_ha:.2f}] t/ha)"
    )

    # Write outputs
    csv_path = write_posterior_csv(summaries, outdir)
    print(f"\nPosterior CSV: {csv_path}")

    # Plots
    plot_traces(sampler, PARAM_NAMES, outdir / "trace_plots.png")
    plot_corner(flat_chain, PARAM_NAMES, outdir / "corner_plot.png")

    # Save chain for reproducibility
    np.save(str(outdir / "flat_chain.npy"), flat_chain)
    print(f"Chain saved: {outdir / 'flat_chain.npy'}")

    return summaries, diag, pred


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bayesian parameter calibration via MCMC (emcee)"
    )
    parser.add_argument(
        "--walkers", type=int, default=32, help="Number of MCMC walkers"
    )
    parser.add_argument("--steps", type=int, default=500, help="Production MCMC steps")
    parser.add_argument(
        "--burn", type=int, default=200, help="Burn-in steps to discard"
    )
    parser.add_argument(
        "--subsample",
        type=int,
        default=10,
        help="Subsample reference every N days",
    )
    parser.add_argument("--outdir", type=Path, default=Path("out/calibration"))
    parser.add_argument("--crop", default="maize", help="Crop preset key")
    parser.add_argument(
        "--climate",
        default="netherlands_temperate",
        help="Climate preset key",
    )
    parser.add_argument("--reference", type=Path, default=None, help="Reference CSV")
    args = parser.parse_args()

    summaries, diag, pred = run_calibration(
        nwalkers=args.walkers,
        nsteps=args.steps,
        burn=args.burn,
        subsample=args.subsample,
        outdir=args.outdir,
        crop_name=args.crop,
        climate_name=args.climate,
        reference_path=args.reference,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
