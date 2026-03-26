#!/usr/bin/env python3
"""Morris sensitivity analysis for AgroGame simulation parameters.

Runs Morris one-at-a-time screening to identify the most influential
parameters on simulation outputs (biomass, LAI, ET, maturity timing).
Uses SALib for sampling and analysis.

Usage:
    poetry run python scripts/sensitivity_analysis.py [--trajectories N] [--outdir DIR]

References:
    Morris (1991): Factorial sampling plans for preliminary computational
    experiments. Technometrics, 33(2), 161-174.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# Parameter definitions: name, default, lower, upper bounds
# Bounds are ±30-50% of default (wider for poorly constrained params).
# ---------------------------------------------------------------------------
PARAM_DEFS: list[dict[str, Any]] = [
    # --- Canopy ---
    {
        "name": "extinction_coefficient_k",
        "group": "canopy",
        "default": 0.65,
        "lo": 0.40,
        "hi": 0.80,
    },
    {"name": "rue_g_per_mj", "group": "canopy", "default": 3.0, "lo": 1.5, "hi": 4.5},
    {
        "name": "sla_m2_per_g",
        "group": "canopy",
        "default": 0.02,
        "lo": 0.012,
        "hi": 0.030,
    },
    {"name": "lai_max", "group": "canopy", "default": 6.0, "lo": 3.0, "hi": 10.0},
    {
        "name": "senescence_rate_per_day",
        "group": "canopy",
        "default": 0.01,
        "lo": 0.002,
        "hi": 0.025,
    },
    {"name": "temp_opt_c", "group": "canopy", "default": 30.0, "lo": 22.0, "hi": 36.0},
    {
        "name": "leaf_fraction_vegetative",
        "group": "canopy",
        "default": 0.7,
        "lo": 0.5,
        "hi": 0.9,
    },
    {
        "name": "harvest_index",
        "group": "canopy",
        "default": 0.50,
        "lo": 0.30,
        "hi": 0.65,
    },
    {
        "name": "remobilization_fraction",
        "group": "canopy",
        "default": 0.02,
        "lo": 0.0,
        "hi": 0.05,
    },
    # --- Phenology ---
    {
        "name": "emergence_gdd",
        "group": "phenology",
        "default": 100.0,
        "lo": 50.0,
        "hi": 200.0,
    },
    {
        "name": "flowering_gdd",
        "group": "phenology",
        "default": 900.0,
        "lo": 600.0,
        "hi": 1200.0,
    },
    {
        "name": "maturity_gdd",
        "group": "phenology",
        "default": 1700.0,
        "lo": 1200.0,
        "hi": 2200.0,
    },
    # --- ET ---
    {"name": "pt_alpha", "group": "et", "default": 1.26, "lo": 1.0, "hi": 1.5},
    {"name": "stage1_limit_mm", "group": "et", "default": 6.0, "lo": 3.0, "hi": 10.0},
    {"name": "ritchie_coef", "group": "et", "default": 3.5, "lo": 2.0, "hi": 5.0},
    {"name": "vpd_sensitivity", "group": "et", "default": 0.15, "lo": 0.05, "hi": 0.30},
    # --- Roots ---
    {
        "name": "max_depth_cm",
        "group": "roots",
        "default": 150.0,
        "lo": 80.0,
        "hi": 200.0,
    },
    {
        "name": "growth_rate_cm_per_day",
        "group": "roots",
        "default": 2.0,
        "lo": 1.0,
        "hi": 3.5,
    },
]

OUTPUT_NAMES = ["final_biomass_g_m2", "peak_lai", "grain_yield_g_m2", "maturity_day"]


def _build_salib_problem() -> dict[str, Any]:
    """Build SALib problem definition from PARAM_DEFS."""
    return {
        "num_vars": len(PARAM_DEFS),
        "names": [p["name"] for p in PARAM_DEFS],
        "bounds": [[p["lo"], p["hi"]] for p in PARAM_DEFS],
    }


def run_model(
    param_values: np.ndarray,
    crop_name: str,
    climate_name: str,
    start: date,
    days: int,
    seed: int = 42,
) -> list[float]:
    """Run a single simulation with overridden parameters.

    Returns [final_biomass, peak_lai, grain_yield, maturity_day].
    """
    from agrogame.atmosphere.et import EtParams
    from agrogame.plant.presets import (
        CropPreset,
        load_crop_presets,
        _load_crop_presets_cached,
    )
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.loader import load_soil_presets
    from agrogame.soil.phenology.params import (
        GrowthStageThresholds,
    )
    from agrogame.soil.water.types import DailyDrivers
    from agrogame.weather.generator import SyntheticWeatherGenerator
    from agrogame.weather.presets import (
        load_climate_presets,
        _load_climate_presets_cached,
    )

    _load_crop_presets_cached.cache_clear()
    _load_climate_presets_cached.cache_clear()

    # Load defaults
    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    base_crop = crops.crops[crop_name]
    climate = climates.climates[climate_name]

    # Map param vector to named values
    vals = {
        PARAM_DEFS[i]["name"]: float(param_values[i]) for i in range(len(PARAM_DEFS))
    }

    # Override CanopyParams
    canopy = replace(
        base_crop.canopy,
        extinction_coefficient_k=vals["extinction_coefficient_k"],
        radiation_use_efficiency_g_per_mj=vals["rue_g_per_mj"],
        specific_leaf_area_m2_per_g=vals["sla_m2_per_g"],
        lai_max=vals["lai_max"],
        senescence_rate_per_day=vals["senescence_rate_per_day"],
        temp_opt_c=vals["temp_opt_c"],
        leaf_fraction_vegetative=vals["leaf_fraction_vegetative"],
        harvest_index=vals["harvest_index"],
        remobilization_fraction=vals["remobilization_fraction"],
    )

    # Override PhenologyParams
    phenology = replace(
        base_crop.phenology,
        thresholds=GrowthStageThresholds(
            emergence_gdd=vals["emergence_gdd"],
            flowering_gdd=vals["flowering_gdd"],
            maturity_gdd=vals["maturity_gdd"],
        ),
    )

    # Override RootParams
    roots = replace(
        base_crop.roots,
        max_depth_cm=vals["max_depth_cm"],
        growth_rate_cm_per_day=vals["growth_rate_cm_per_day"],
    )

    # Override EtParams
    et_params = EtParams(
        pt_alpha=vals["pt_alpha"],
        stage1_limit_mm=vals["stage1_limit_mm"],
        ritchie_coef=vals["ritchie_coef"],
        vpd_sensitivity=vals["vpd_sensitivity"],
    )

    crop = CropPreset(
        name=base_crop.name,
        phenology=phenology,
        canopy=canopy,
        roots=roots,
    )

    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, start)

    orch = FullSimulationOrchestrator(
        profile,
        crop=crop,
        latitude_deg=climate.latitude_deg,
        et_params=et_params,
    )

    peak_lai = 0.0
    maturity_day = float(days)
    for i, rec in enumerate(series.records):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )
        peak_lai = max(peak_lai, orch.canopy.state.lai)
        if orch.phenology.state.stage.name == "MATURITY" and maturity_day == float(
            days
        ):
            maturity_day = float(i + 1)

    return [
        orch.canopy.state.biomass_g_m2,
        peak_lai,
        orch.canopy.state.grain_biomass_g_m2,
        maturity_day,
    ]


def run_morris(
    crop_name: str,
    climate_name: str,
    start: date,
    days: int,
    trajectories: int = 100,
    seed: int = 42,
) -> dict[str, Any]:
    """Run Morris screening and return analysis results."""
    from SALib.sample import morris as morris_sample
    from SALib.analyze import morris as morris_analyze

    problem = _build_salib_problem()
    X = morris_sample.sample(problem, N=trajectories, seed=seed)

    n_runs = X.shape[0]
    Y = np.zeros((n_runs, len(OUTPUT_NAMES)))

    for i in range(n_runs):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"  Run {i + 1}/{n_runs}...", file=sys.stderr)
        Y[i, :] = run_model(X[i, :], crop_name, climate_name, start, days, seed)

    results = {}
    for j, output_name in enumerate(OUTPUT_NAMES):
        si = morris_analyze.analyze(problem, X, Y[:, j], print_to_console=False)
        results[output_name] = {
            "mu_star": si["mu_star"],
            "sigma": si["sigma"],
            "names": si["names"],
        }

    return results


def write_results_csv(
    results: dict[str, Any],
    scenario_label: str,
    outdir: Path,
) -> Path:
    """Write ranked parameter importance to CSV."""
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / f"sensitivity_{scenario_label}.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["output", "rank", "parameter", "mu_star", "sigma"])
        for output_name, si in results.items():
            order = np.argsort(-np.array(si["mu_star"]))
            for rank, idx in enumerate(order):
                writer.writerow(
                    [
                        output_name,
                        rank + 1,
                        si["names"][idx],
                        f"{si['mu_star'][idx]:.4f}",
                        f"{si['sigma'][idx]:.4f}",
                    ]
                )
    print(f"Saved {csv_path}")
    return csv_path


def write_tornado_plot(
    results: dict[str, Any],
    scenario_label: str,
    outdir: Path,
) -> Path | None:
    """Generate tornado plot of μ* for final_biomass. Requires matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available — skipping tornado plot", file=sys.stderr)
        return None

    outdir.mkdir(parents=True, exist_ok=True)
    si = results["final_biomass_g_m2"]
    order = np.argsort(si["mu_star"])
    names = [si["names"][i] for i in order]
    mu_star = [si["mu_star"][i] for i in order]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(range(len(names)), mu_star, color="#4c78a8")
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel("μ* (mean absolute elementary effect)")
    ax.set_title(f"Morris Sensitivity — {scenario_label}\n(final biomass)")
    fig.tight_layout()

    png_path = outdir / f"tornado_{scenario_label}.png"
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    print(f"Saved {png_path}")
    return png_path


def top_n_parameters(results: dict[str, Any], n: int = 5) -> dict[str, list[str]]:
    """Return top-N most influential parameters per output."""
    top = {}
    for output_name, si in results.items():
        order = np.argsort(-np.array(si["mu_star"]))[:n]
        top[output_name] = [si["names"][i] for i in order]
    return top


def main() -> None:
    parser = argparse.ArgumentParser(description="Morris sensitivity analysis")
    parser.add_argument(
        "--trajectories",
        type=int,
        default=100,
        help="Morris trajectories (default 100)",
    )
    parser.add_argument(
        "--outdir", type=str, default="out/sensitivity", help="Output directory"
    )
    args = parser.parse_args()

    outdir = Path(args.outdir)
    scenarios = [
        ("maize", "netherlands_temperate", date(2024, 4, 1), 150, "maize_nl"),
        ("maize", "sahel_arid", date(2024, 6, 1), 150, "maize_sahel"),
    ]

    all_top5: dict[str, dict[str, list[str]]] = {}
    for crop, climate, start, days, label in scenarios:
        print(f"\n=== {label} ({args.trajectories} trajectories) ===", file=sys.stderr)
        results = run_morris(crop, climate, start, days, args.trajectories)
        write_results_csv(results, label, outdir)
        write_tornado_plot(results, label, outdir)
        all_top5[label] = top_n_parameters(results)

    # Print summary
    print("\n=== Top 5 parameters per output ===")
    for label, top in all_top5.items():
        print(f"\n{label}:")
        for output, params in top.items():
            print(f"  {output}: {', '.join(params)}")


if __name__ == "__main__":
    main()
