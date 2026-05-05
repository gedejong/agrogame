from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.plant.stress import StressCalculator
from agrogame.sim.builder import generate_rain_evap


def simulate_nitrogen(
    profile_name: str,
    days: int,
    rainfall_mm: float,
    evaporation_mm: float,
    pattern: str = "constant",
) -> tuple[list[float], list[float], list[float], list[float]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    orch = FullSimulationOrchestrator(profile)
    calc = StressCalculator()

    total_org: list[float] = []
    total_nh4: list[float] = []
    total_no3: list[float] = []
    n_stress: list[float] = []

    rains, evaps = generate_rain_evap(days, rainfall_mm, evaporation_mm, pattern)

    prev_min: float | None = None
    for i in range(days):
        prev_min = (
            prev_min
            if prev_min is not None
            else (sum(orch.n_state.nh4) + sum(orch.n_state.no3))
        )
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=15.0,
            tmax_c=25.0,
            par_mj_m2=12.0,
            plant_n_demand_kg_ha=1.0,
        )
        current_min = sum(orch.n_state.nh4) + sum(orch.n_state.no3)
        uptake_proxy = max(0.0, prev_min - current_min)
        n_stress.append(calc.nutrient_from_uptake_demand(uptake_proxy, 1.0))
        prev_min = current_min

        total_org.append(sum(orch.n_state.organic_n))
        total_nh4.append(sum(orch.n_state.nh4))
        total_no3.append(sum(orch.n_state.no3))

    return total_org, total_nh4, total_no3, n_stress


def simulate_phosphorus(
    profile_name: str,
    days: int,
    rainfall_mm: float,
    evaporation_mm: float,
    pattern: str = "constant",
) -> tuple[list[float], list[float], list[float], list[float]]:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils[profile_name]
    orch = FullSimulationOrchestrator(profile)

    total_org: list[float] = []
    total_avail: list[float] = []
    total_fixed: list[float] = []
    p_stress_series: list[float] = []

    rains, evaps = generate_rain_evap(days, rainfall_mm, evaporation_mm, pattern)

    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=15.0,
            tmax_c=25.0,
            par_mj_m2=12.0,
            target_ph=6.8,
        )
        total_org.append(sum(orch.p_state.organic_p))
        total_avail.append(sum(orch.p_state.available_p))
        total_fixed.append(sum(orch.p_state.fixed_p))
        try:
            avail = total_avail[-1]
            baseline = max(1e-6, total_avail[0])
            p_stress = max(0.0, min(1.0, avail / baseline))
        except Exception:
            p_stress = 1.0
        p_stress_series.append(p_stress)

    return total_org, total_avail, total_fixed, p_stress_series


def plot_nitrogen_timeseries(
    profile: str,
    days: int,
    rain: float,
    evap: float,
    out: Path,
    pattern: str = "constant",
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    total_org, total_nh4, total_no3, n_stress = simulate_nitrogen(
        profile_name=profile,
        days=days,
        rainfall_mm=rain,
        evaporation_mm=evap,
        pattern=pattern,
    )

    x = list(range(1, days + 1))
    plt.figure(figsize=(10, 7))
    plt.plot(x, total_org, label="organic N (kg/ha)")
    plt.plot(x, total_nh4, label="NH4 (kg/ha)")
    plt.plot(x, total_no3, label="NO3 (kg/ha)")
    ax2 = plt.gca().twinx()
    ax2.plot(x, n_stress, color="#2ca02c", linestyle="--", label="N stress (-)")
    ax2.set_ylim(0.0, 1.05)
    plt.xlabel("Day")
    plt.ylabel("N mass (kg/ha)")
    plt.title(f"Nitrogen pools and stress – {profile} ({pattern})")
    h1, l1 = plt.gca().get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    plt.legend(h1 + h2, l1 + l2, loc="upper left")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print("Saved", out)


def plot_phosphorus_timeseries(
    profile: str,
    days: int,
    rain: float,
    evap: float,
    out: Path,
    pattern: str = "constant",
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    total_org, total_avail, total_fixed, p_stress = simulate_phosphorus(
        profile_name=profile,
        days=days,
        rainfall_mm=rain,
        evaporation_mm=evap,
        pattern=pattern,
    )
    x = list(range(1, days + 1))
    plt.figure(figsize=(10, 7))
    plt.plot(x, total_org, label="organic P (kg/ha)")
    plt.plot(x, total_avail, label="available P (kg/ha)")
    plt.plot(x, total_fixed, label="fixed P (kg/ha)")
    ax2 = plt.gca().twinx()
    ax2.plot(x, p_stress, color="#bcbd22", linestyle="--", label="P stress (-)")
    ax2.set_ylim(0.0, 1.05)
    plt.xlabel("Day")
    plt.ylabel("P mass (kg/ha)")
    plt.title(f"Phosphorus pools and stress – {profile} ({pattern})")
    h1, l1 = plt.gca().get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    seen = set()
    handles: list = []
    labels: list[str] = []
    for handle, label in list(zip(h1 + h2, l1 + l2, strict=False)):
        if label not in seen:
            seen.add(label)
            handles.append(handle)
            labels.append(label)
    plt.legend(handles, labels, loc="upper left")
    plt.tight_layout()
    plt.savefig(out, dpi=150)
    print("Saved", out)
