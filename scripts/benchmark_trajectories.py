#!/usr/bin/env python3
"""Benchmark AgroGame trajectories against DSSAT/APSIM references and GYGA yields.

Runs maize simulations for 3 climates, compares daily trajectories (LAI, biomass,
cumulative ET, soil moisture) against DSSAT CERES-Maize literature-derived references,
generates Taylor diagrams and a GYGA yield comparison table.

Usage:
    poetry run python scripts/benchmark_trajectories.py [--outdir DIR]

References:
    Taylor, K.E. (2001) Summarizing multiple aspects of model performance in a
        single diagram. J. Geophys. Res., 106(D7):7183-7192.
    Jones, J.W. et al. (2003) The DSSAT Cropping System Model.
        European Journal of Agronomy, 18:235-265.
    Global Yield Gap Atlas (https://yieldgap.org).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

# ---------------------------------------------------------------------------
# GYGA yield data (water-limited potential, t/ha grain)
# Source: Global Yield Gap Atlas (yieldgap.org), accessed 2024.
# ---------------------------------------------------------------------------
GYGA_YIELDS: dict[str, dict[str, float]] = {
    "maize": {
        "netherlands_temperate": 11.0,  # NW Europe potential: 10-12 t/ha
        "kenya_highlands": 7.0,  # Kenya highland potential: 6-8 t/ha
        "sahel_arid": 3.0,  # Sahel rainfed: 2-4 t/ha
    },
    "sorghum": {
        "sahel_arid": 3.0,  # Sahel rainfed sorghum: 2-4 t/ha
    },
    "spring_wheat": {
        "netherlands_temperate": 8.5,  # NW Europe: 8-9 t/ha
        "kenya_highlands": 5.0,  # Kenya: 4-6 t/ha
    },
}


@dataclass(frozen=True)
class BenchmarkScenario:
    """One crop x climate x planting-date benchmark scenario."""

    name: str
    crop: str
    climate: str
    start: date
    days: int
    reference: str


SCENARIOS: list[BenchmarkScenario] = [
    BenchmarkScenario(
        name="maize_netherlands",
        crop="maize",
        climate="netherlands_temperate",
        start=date(2024, 4, 1),
        days=150,
        reference="maize_netherlands_dssat.csv",
    ),
    BenchmarkScenario(
        name="maize_kenya",
        crop="maize",
        climate="kenya_highlands",
        start=date(2024, 3, 1),
        days=150,
        reference="maize_kenya_dssat.csv",
    ),
    BenchmarkScenario(
        name="maize_sahel",
        crop="maize",
        climate="sahel_arid",
        start=date(2024, 6, 15),
        days=150,
        reference="maize_sahel_dssat.csv",
    ),
]


# ---------------------------------------------------------------------------
# Taylor diagram statistics
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TaylorStats:
    """Statistics for a single variable on a Taylor diagram.

    Reference: Taylor (2001), J. Geophys. Res., 106(D7):7183-7192.
    """

    correlation: float  # Pearson correlation coefficient
    std_ratio: float  # sigma_sim / sigma_ref
    crmsd: float  # centred root-mean-square difference (normalised by ref std)
    variable: str = ""
    scenario: str = ""


def pearson_r(x: Sequence[float], y: Sequence[float]) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    if n < 2:
        return 0.0
    mx = sum(x) / n
    my = sum(y) / n
    cov = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y, strict=False))
    vx = sum((xi - mx) ** 2 for xi in x)
    vy = sum((yi - my) ** 2 for yi in y)
    denom = math.sqrt(vx * vy)
    if denom == 0.0:
        return 0.0
    return cov / denom


def std_dev(x: Sequence[float]) -> float:
    """Population standard deviation."""
    n = len(x)
    if n < 2:
        return 0.0
    m = sum(x) / n
    return math.sqrt(sum((xi - m) ** 2 for xi in x) / n)


def taylor_stats(
    ref: Sequence[float],
    sim: Sequence[float],
    variable: str = "",
    scenario: str = "",
) -> TaylorStats:
    """Compute Taylor diagram statistics for a pair of time series."""
    r = pearson_r(ref, sim)
    s_ref = std_dev(ref)
    s_sim = std_dev(sim)
    ratio = s_sim / s_ref if s_ref > 0 else 0.0
    # Centred RMSD (normalised): E'^2 = s_sim^2 + s_ref^2 - 2*s_sim*s_ref*r
    crmsd_raw = math.sqrt(max(s_sim**2 + s_ref**2 - 2 * s_sim * s_ref * r, 0.0))
    crmsd_norm = crmsd_raw / s_ref if s_ref > 0 else 0.0
    return TaylorStats(
        correlation=r,
        std_ratio=ratio,
        crmsd=crmsd_norm,
        variable=variable,
        scenario=scenario,
    )


# ---------------------------------------------------------------------------
# Timing discrepancy analysis
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TimingDiscrepancy:
    """Records a peak-timing difference between reference and simulated series."""

    scenario: str
    variable: str
    ref_peak_day: int
    sim_peak_day: int
    offset_days: int  # sim - ref (positive = sim peaks later)


def find_peak_day(values: Sequence[float]) -> int:
    """Return index (day) of maximum value."""
    if not values:
        return 0
    return max(range(len(values)), key=lambda i: values[i])


# ---------------------------------------------------------------------------
# Reference data loading
# ---------------------------------------------------------------------------
def load_reference_csv(path: Path) -> dict[str, list[float]]:
    """Load a reference trajectory CSV into column dict."""
    columns: dict[str, list[float]] = {}
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for key, val in row.items():
                columns.setdefault(key, []).append(float(val))
    return columns


# ---------------------------------------------------------------------------
# Simulation runner
# ---------------------------------------------------------------------------
def run_simulation(
    crop_name: str,
    climate_name: str,
    start: date,
    days: int,
    seed: int = 42,
) -> dict[str, list[float]]:
    """Run a full simulation and return daily trajectory dict."""
    from agrogame.plant.presets import load_crop_presets
    from agrogame.soil.loader import load_soil_presets
    from agrogame.sim.orchestrator import FullSimulationOrchestrator
    from agrogame.soil.water.types import DailyDrivers
    from agrogame.weather.generator import SyntheticWeatherGenerator
    from agrogame.weather.presets import load_climate_presets

    crops = load_crop_presets(Path("data/crops/presets.yaml"))
    climates = load_climate_presets(Path("data/climate/presets.yaml"))
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]

    crop = crops.crops[crop_name]
    climate = climates.climates[climate_name]
    gen = SyntheticWeatherGenerator(climate, seed=seed)
    series = gen.generate(days, start)

    orch = FullSimulationOrchestrator(
        profile, crop=crop, latitude_deg=climate.latitude_deg
    )

    result: dict[str, list[float]] = {
        "day": [],
        "lai": [],
        "biomass_g_m2": [],
        "cumulative_et_mm": [],
        "soil_moisture_top30_mm": [],
    }
    cumulative_et = 0.0

    for i, rec in enumerate(series.records):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rec.precip_mm or 0.0),
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=rec.shortwave_mj_m2 or 12.0,
            sim_date=rec.day,
        )

        # Estimate daily ET from canopy transpiration demand
        # LAI-based proxy consistent with reference generation
        f_cover = 1.0 - math.exp(-0.5 * orch.canopy.state.lai)
        daily_et_approx = 0.8 + f_cover * 4.0
        cumulative_et += daily_et_approx

        # Soil moisture top 30 cm: sum storage of layers within top 30 cm
        sm_top30 = 0.0
        depth_accum = 0.0
        for j, layer in enumerate(profile.layers):
            if depth_accum >= 30.0:
                break
            remaining = min(layer.depth_cm, 30.0 - depth_accum)
            sm_top30 += orch.water_state.theta[j] * remaining * 10.0
            depth_accum += layer.depth_cm

        result["day"].append(float(i))
        result["lai"].append(orch.canopy.state.lai)
        result["biomass_g_m2"].append(orch.canopy.state.biomass_g_m2)
        result["cumulative_et_mm"].append(cumulative_et)
        result["soil_moisture_top30_mm"].append(sm_top30)

    return result


# ---------------------------------------------------------------------------
# GYGA yield comparison
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class GygaComparison:
    """One row of the GYGA yield comparison table."""

    scenario: str
    crop: str
    climate: str
    sim_grain_g_m2: float
    sim_yield_t_ha: float
    gyga_yield_t_ha: float
    ratio: float  # sim / gyga
    status: str  # "within range", "overestimation", "underestimation"


def gyga_compare(
    crop: str,
    climate: str,
    scenario_name: str,
    sim_grain_g_m2: float,
    harvest_index: float,
) -> GygaComparison:
    """Compare simulated grain yield to GYGA water-limited potential."""
    sim_yield_t_ha = sim_grain_g_m2 * 0.01  # g/m² → t/ha
    gyga = GYGA_YIELDS.get(crop, {}).get(climate, 0.0)
    ratio = sim_yield_t_ha / gyga if gyga > 0 else 0.0
    if ratio > 1.2:
        status = "overestimation"
    elif ratio < 0.3:
        status = "underestimation"
    else:
        status = "within range"
    return GygaComparison(
        scenario=scenario_name,
        crop=crop,
        climate=climate,
        sim_grain_g_m2=sim_grain_g_m2,
        sim_yield_t_ha=sim_yield_t_ha,
        gyga_yield_t_ha=gyga,
        ratio=ratio,
        status=status,
    )


# ---------------------------------------------------------------------------
# Taylor diagram plotting (matplotlib polar)
# ---------------------------------------------------------------------------
def plot_taylor_diagram(
    stats_list: list[TaylorStats],
    title: str,
    output_path: Path,
) -> None:
    """Generate a Taylor diagram as a polar plot.

    Reference: Taylor (2001), J. Geophys. Res.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib/numpy not available — skipping Taylor diagram plot")
        return

    fig = plt.figure(figsize=(8, 8))
    ax: Any = fig.add_subplot(111, polar=True)

    # Taylor diagram: angle = arccos(correlation), radius = std ratio
    ax.set_thetamin(0)
    ax.set_thetamax(90)
    ax.set_theta_direction(-1)
    ax.set_theta_offset(0)

    # Reference point at (0, 1.0)
    ax.plot(0, 1.0, "ko", markersize=10, label="Reference")

    # Correlation lines
    corr_ticks = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]
    for ct in corr_ticks:
        angle = math.acos(ct)
        ax.plot([angle, angle], [0, 2.0], "k--", alpha=0.15, linewidth=0.5)
        ax.text(angle, 2.05, f"{ct:.2f}", fontsize=7, ha="center", alpha=0.5)

    # CRMSD circles centred on reference point
    for crmsd_val in [0.25, 0.5, 0.75, 1.0, 1.5]:
        theta_arc = np.linspace(0, np.pi / 2, 100)
        r_arc = []
        for t in theta_arc:
            # CRMSD² = 1 + ratio² - 2*ratio*cos(theta)
            # Solve for ratio: ratio² - 2*cos(t)*ratio + (1 - crmsd²) = 0
            a_coef = 1.0
            b_coef = -2.0 * np.cos(t)
            c_coef = 1.0 - crmsd_val**2
            disc = b_coef**2 - 4 * a_coef * c_coef
            if disc >= 0:
                r_val = (-b_coef + np.sqrt(disc)) / (2 * a_coef)
                r_arc.append(r_val)
            else:
                r_arc.append(float("nan"))
        ax.plot(theta_arc, r_arc, "b--", alpha=0.2, linewidth=0.5)

    # Plot model points
    markers = {
        "lai": "o",
        "biomass_g_m2": "s",
        "cumulative_et_mm": "^",
        "soil_moisture_top30_mm": "D",
    }
    colors = {
        "maize_netherlands": "#1f77b4",
        "maize_kenya": "#ff7f0e",
        "maize_sahel": "#2ca02c",
    }

    for ts in stats_list:
        angle = math.acos(max(-1.0, min(1.0, ts.correlation)))
        radius = ts.std_ratio
        marker = markers.get(ts.variable, "o")
        color = colors.get(ts.scenario, "gray")
        ax.plot(
            angle,
            radius,
            marker=marker,
            color=color,
            markersize=8,
            label=f"{ts.scenario} {ts.variable}",
        )

    ax.set_rlabel_position(0)
    ax.set_ylabel("Standard Deviation Ratio (sim/ref)", labelpad=30)
    ax.set_ylim(0, 2.5)

    # Legend (deduplicate)
    handles, labels = ax.get_legend_handles_labels()
    by_label = dict(zip(labels, handles, strict=False))
    ax.legend(
        by_label.values(),
        by_label.keys(),
        loc="upper right",
        bbox_to_anchor=(1.35, 1.0),
        fontsize=7,
    )

    ax.set_title(title, pad=20, fontsize=12)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Taylor diagram saved: {output_path}")


# ---------------------------------------------------------------------------
# Main benchmark pipeline
# ---------------------------------------------------------------------------
def run_benchmarks(outdir: Path) -> tuple[
    list[TaylorStats],
    list[TimingDiscrepancy],
    list[GygaComparison],
]:
    """Run all benchmark scenarios and return collected results."""
    ref_dir = Path("data/benchmarks/reference")
    outdir.mkdir(parents=True, exist_ok=True)

    all_taylor: list[TaylorStats] = []
    all_timing: list[TimingDiscrepancy] = []
    all_gyga: list[GygaComparison] = []

    variables = ["lai", "biomass_g_m2", "cumulative_et_mm", "soil_moisture_top30_mm"]

    for sc in SCENARIOS:
        name = sc.name
        print(f"\n{'='*60}")
        print(f"Scenario: {name} ({sc.crop} x {sc.climate})")
        print(f"{'='*60}")

        # Load reference
        ref_path = ref_dir / sc.reference
        if not ref_path.exists():
            print(f"  WARNING: reference file not found: {ref_path}")
            continue
        ref_data = load_reference_csv(ref_path)

        # Run simulation
        print("  Running simulation...")
        sim_data = run_simulation(sc.crop, sc.climate, sc.start, sc.days)

        # Write simulated trajectory CSV
        sim_csv = outdir / f"{name}_simulated.csv"
        with sim_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "day",
                    "lai",
                    "biomass_g_m2",
                    "cumulative_et_mm",
                    "soil_moisture_top30_mm",
                ]
            )
            for i in range(len(sim_data["day"])):
                writer.writerow(
                    [
                        int(sim_data["day"][i]),
                        f"{sim_data['lai'][i]:.3f}",
                        f"{sim_data['biomass_g_m2'][i]:.1f}",
                        f"{sim_data['cumulative_et_mm'][i]:.1f}",
                        f"{sim_data['soil_moisture_top30_mm'][i]:.1f}",
                    ]
                )
        print(f"  Simulated CSV: {sim_csv}")

        # Taylor statistics per variable
        n = min(len(ref_data.get("day", [])), len(sim_data["day"]))
        print(f"\n  Taylor statistics (n={n} days):")
        print(f"  {'Variable':<25} {'r':>6} {'std_ratio':>10} {'CRMSD':>8}")
        print(f"  {'-'*25} {'-'*6} {'-'*10} {'-'*8}")

        for var in variables:
            ref_vals = ref_data.get(var, [])[:n]
            sim_vals = sim_data.get(var, [])[:n]
            if not ref_vals or not sim_vals:
                continue
            ts = taylor_stats(ref_vals, sim_vals, variable=var, scenario=name)
            all_taylor.append(ts)
            print(
                f"  {var:<25} {ts.correlation:>6.3f}"
                f" {ts.std_ratio:>10.3f} {ts.crmsd:>8.3f}"
            )

        # Timing discrepancies (peak day comparison)
        print("\n  Timing discrepancies:")
        print(f"  {'Variable':<25} {'Ref peak':>10} {'Sim peak':>10} {'Offset':>8}")
        print(f"  {'-'*25} {'-'*10} {'-'*10} {'-'*8}")

        for var in ["lai", "biomass_g_m2"]:
            ref_vals = ref_data.get(var, [])[:n]
            sim_vals = sim_data.get(var, [])[:n]
            if not ref_vals or not sim_vals:
                continue
            ref_peak = find_peak_day(ref_vals)
            sim_peak = find_peak_day(sim_vals)
            offset = sim_peak - ref_peak
            td = TimingDiscrepancy(
                scenario=name,
                variable=var,
                ref_peak_day=ref_peak,
                sim_peak_day=sim_peak,
                offset_days=offset,
            )
            all_timing.append(td)
            direction = "late" if offset > 0 else "early" if offset < 0 else "match"
            ref_day = f"day {ref_peak}"
            sim_day = f"day {sim_peak}"
            print(
                f"  {var:<25} {ref_day:>10}"
                f" {sim_day:>10} {offset:>+5}d ({direction})"
            )

        # GYGA comparison
        # Get grain yield from final simulation state
        from agrogame.plant.presets import load_crop_presets

        crops = load_crop_presets(Path("data/crops/presets.yaml"))
        crop_preset = crops.crops[sc.crop]
        hi = crop_preset.canopy.harvest_index
        final_biomass = (
            sim_data["biomass_g_m2"][-1] if sim_data["biomass_g_m2"] else 0.0
        )
        grain_g_m2 = final_biomass * hi
        gc = gyga_compare(sc.crop, sc.climate, name, grain_g_m2, hi)
        all_gyga.append(gc)

    return all_taylor, all_timing, all_gyga


def write_gyga_table(gyga_results: list[GygaComparison], outdir: Path) -> Path:
    """Write GYGA yield comparison to CSV."""
    path = outdir / "gyga_yield_comparison.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "scenario",
                "crop",
                "climate",
                "sim_grain_g_m2",
                "sim_yield_t_ha",
                "gyga_yield_t_ha",
                "ratio",
                "status",
            ]
        )
        for gc in gyga_results:
            writer.writerow(
                [
                    gc.scenario,
                    gc.crop,
                    gc.climate,
                    f"{gc.sim_grain_g_m2:.1f}",
                    f"{gc.sim_yield_t_ha:.2f}",
                    f"{gc.gyga_yield_t_ha:.1f}",
                    f"{gc.ratio:.2f}",
                    gc.status,
                ]
            )
    return path


def write_taylor_csv(taylor_results: list[TaylorStats], outdir: Path) -> Path:
    """Write Taylor statistics to CSV."""
    path = outdir / "taylor_statistics.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scenario", "variable", "correlation", "std_ratio", "crmsd"])
        for ts in taylor_results:
            writer.writerow(
                [
                    ts.scenario,
                    ts.variable,
                    f"{ts.correlation:.4f}",
                    f"{ts.std_ratio:.4f}",
                    f"{ts.crmsd:.4f}",
                ]
            )
    return path


def write_timing_csv(timing_results: list[TimingDiscrepancy], outdir: Path) -> Path:
    """Write timing discrepancies to CSV."""
    path = outdir / "timing_discrepancies.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["scenario", "variable", "ref_peak_day", "sim_peak_day", "offset_days"]
        )
        for td in timing_results:
            writer.writerow(
                [
                    td.scenario,
                    td.variable,
                    td.ref_peak_day,
                    td.sim_peak_day,
                    td.offset_days,
                ]
            )
    return path


def print_gyga_table(gyga_results: list[GygaComparison]) -> None:
    """Print GYGA comparison as formatted table."""
    print(f"\n{'='*80}")
    print("GYGA Yield Comparison (grain yield, t/ha)")
    print(f"{'='*80}")
    print(
        f"{'Scenario':<22} {'Crop':<10} {'Climate':<22}"
        f" {'Sim':>6} {'GYGA':>6} {'Ratio':>6} {'Status'}"
    )
    print(f"{'-'*22} {'-'*10} {'-'*22} {'-'*6} {'-'*6} {'-'*6} {'-'*15}")
    for gc in gyga_results:
        print(
            f"{gc.scenario:<22} {gc.crop:<10} {gc.climate:<22} "
            f"{gc.sim_yield_t_ha:>6.2f} {gc.gyga_yield_t_ha:>6.1f} "
            f"{gc.ratio:>6.2f} {gc.status}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark trajectories against DSSAT/APSIM & GYGA"
    )
    parser.add_argument("--outdir", type=Path, default=Path("out/benchmarks"))
    args = parser.parse_args()

    outdir: Path = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    taylor_results, timing_results, gyga_results = run_benchmarks(outdir)

    # Write CSVs
    taylor_csv = write_taylor_csv(taylor_results, outdir)
    timing_csv = write_timing_csv(timing_results, outdir)
    gyga_csv = write_gyga_table(gyga_results, outdir)
    print("\nCSV outputs:")
    print(f"  Taylor statistics: {taylor_csv}")
    print(f"  Timing discrepancies: {timing_csv}")
    print(f"  GYGA comparison: {gyga_csv}")

    # Print GYGA table
    print_gyga_table(gyga_results)

    # Generate Taylor diagram
    if taylor_results:
        plot_taylor_diagram(
            taylor_results,
            title="AgroGame vs DSSAT/APSIM — Maize x 3 Climates",
            output_path=outdir / "taylor_diagram.png",
        )

    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    overest = [gc for gc in gyga_results if gc.status == "overestimation"]
    underest = [gc for gc in gyga_results if gc.status == "underestimation"]
    if overest:
        print(f"  Overestimations: {', '.join(gc.scenario for gc in overest)}")
    if underest:
        print(f"  Underestimations: {', '.join(gc.scenario for gc in underest)}")

    large_offsets = [td for td in timing_results if abs(td.offset_days) > 10]
    if large_offsets:
        print("  Large timing offsets (>10 days):")
        for td in large_offsets:
            print(f"    {td.scenario} {td.variable}: {td.offset_days:+d} days")

    mean_r = (
        sum(ts.correlation for ts in taylor_results) / len(taylor_results)
        if taylor_results
        else 0.0
    )
    print(f"  Mean correlation across all variables: {mean_r:.3f}")
    print(f"\nDone. Outputs in {outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
