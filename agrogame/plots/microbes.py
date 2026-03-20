from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from agrogame.sim.builder import (
    build_full_from_preset,
    generate_rain_evap,
    generate_temp_par,
)
from agrogame.soil.water.types import DailyDrivers
from agrogame.soil.microbes.events import (
    MicrobialSnapshot,
    EnzymeProduced,
    EnzymeGroupTotals,
    MicrobialActivityComputed,
)


def _ensure_out(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)


def plot_microbes_timeseries(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    latest_c: float = 0.0
    latest_n: float = 0.0
    latest_enzyme_total: float = 0.0

    def _on_snapshot(ev: MicrobialSnapshot) -> None:
        nonlocal latest_c, latest_n
        latest_c = float(ev.total_c_kg_ha)
        latest_n = float(ev.total_n_kg_ha)

    def _on_enzyme_totals(ev: EnzymeGroupTotals) -> None:
        nonlocal latest_enzyme_total
        latest_enzyme_total = float(sum(ev.totals_c_kg_ha_by_group.values()))

    bus.subscribe(MicrobialSnapshot, _on_snapshot)
    bus.subscribe(EnzymeGroupTotals, _on_enzyme_totals)

    org: list[float] = []
    active: list[float] = []
    enzyme: list[float] = []

    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    for i in range(days):
        latest_enzyme_total = 0.0
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
        org.append(latest_c)
        active.append(latest_n)
        enzyme.append(latest_enzyme_total)

    x = list(range(1, days + 1))
    plt.figure(figsize=(10, 6))
    plt.plot(x, org, label="Organic C (kg/ha)")
    plt.plot(x, active, label="Active biomass (kg/ha)")
    plt.plot(x, enzyme, label="Enzyme cost (kg/ha)")
    plt.xlabel("Day")
    plt.ylabel("kg/ha")
    plt.title("Microbes timeseries")
    plt.legend()
    plt.tight_layout()
    path = out_dir / "microbes_timeseries.png"
    plt.savefig(path, dpi=150)
    print("Saved", path)


def plot_microbes_depth(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    enzyme_by_layer: dict[int, float] = {}

    def _on_enzyme(ev: EnzymeProduced) -> None:
        enzyme_by_layer[ev.layer] = enzyme_by_layer.get(ev.layer, 0.0) + float(
            ev.production_cost_c_kg_ha
        )

    bus.subscribe(EnzymeProduced, _on_enzyme)
    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
    n_layers = len(orch.profile.layers)
    vals = [enzyme_by_layer.get(i, 0.0) for i in range(n_layers)]
    y = list(range(len(vals)))
    plt.figure(figsize=(8, 6))
    plt.step(vals, y)
    plt.xlabel("Enzyme pool (kg/ha)")
    plt.ylabel("Layer")
    plt.title("Microbial enzyme by depth")
    plt.tight_layout()
    path = out_dir / "microbes_depth.png"
    plt.savefig(path, dpi=150)
    print("Saved", path)


def plot_microbes_split(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    totals: dict[str, float] = {}

    def _on_totals(ev: EnzymeGroupTotals) -> None:
        totals.clear()
        totals.update(ev.totals_c_kg_ha_by_group)

    bus.subscribe(EnzymeGroupTotals, _on_totals)
    org: list[float] = []
    active: list[float] = []
    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    latest_c: float = 0.0
    latest_n: float = 0.0
    bus.subscribe(MicrobialSnapshot, lambda ev: None)

    def _on_snapshot(ev: MicrobialSnapshot) -> None:
        nonlocal latest_c, latest_n
        latest_c = float(ev.total_c_kg_ha)
        latest_n = float(ev.total_n_kg_ha)

    bus.subscribe(MicrobialSnapshot, _on_snapshot)
    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
        org.append(latest_c)
        active.append(latest_n)
    x = list(range(1, days + 1))
    fig, axs = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    axs[0].plot(x, org, label="Microbial C")
    axs[0].legend()
    axs[1].plot(x, active, label="Microbial N")
    axs[1].legend()
    for a in axs:
        a.set_ylabel("kg/ha")
    axs[1].set_xlabel("Day")
    fig.tight_layout()
    path = out_dir / "microbes_split.png"
    fig.savefig(path, dpi=150)
    print("Saved", path)


def plot_microbes_enzyme_depth(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    enzyme_by_layer: dict[int, float] = {}

    def _on_enzyme(ev: EnzymeProduced) -> None:
        enzyme_by_layer[ev.layer] = enzyme_by_layer.get(ev.layer, 0.0) + float(
            ev.production_cost_c_kg_ha
        )

    bus.subscribe(EnzymeProduced, _on_enzyme)
    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
    n_layers = len(orch.profile.layers)
    vals = [enzyme_by_layer.get(i, 0.0) for i in range(n_layers)]
    y = list(range(len(vals)))
    plt.figure(figsize=(8, 6))
    plt.step(vals, y)
    plt.xlabel("Enzyme cost (kg/ha)")
    plt.ylabel("Layer")
    plt.title("Microbial enzyme by depth")
    plt.tight_layout()
    path = out_dir / "microbes_enzyme_depth.png"
    plt.savefig(path, dpi=150)
    print("Saved", path)


def plot_microbes_activity_depth(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    latest_activity_by_layer: dict[int, float] = {}

    def _on_activity(ev: MicrobialActivityComputed) -> None:
        latest_activity_by_layer[int(ev.layer)] = float(ev.activity_index)

    bus.subscribe(MicrobialActivityComputed, _on_activity)
    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
    n_layers = len(orch.profile.layers)
    vals = [latest_activity_by_layer.get(i, 0.0) for i in range(n_layers)]
    y = list(range(len(vals)))
    plt.figure(figsize=(8, 6))
    plt.step(vals, y)
    plt.xlabel("Activity index (-)")
    plt.ylabel("Layer")
    plt.title("Microbial activity by depth")
    plt.tight_layout()
    path = out_dir / "microbes_activity_depth.png"
    plt.savefig(path, dpi=150)
    print("Saved", path)


def plot_microbes_activity_surface(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    activity_surface_series: list[float] = []
    latest_activity_by_layer: dict[int, float] = {}

    def _on_activity(ev: MicrobialActivityComputed) -> None:
        latest_activity_by_layer[int(ev.layer)] = float(ev.activity_index)

    bus.subscribe(MicrobialActivityComputed, _on_activity)
    x = list(range(1, days + 1))
    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    for i in range(days):
        latest_activity_by_layer.clear()
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
        activity_surface_series.append(sum(latest_activity_by_layer.values()))
    plt.figure(figsize=(10, 5))
    plt.plot(x, activity_surface_series, label="Activity surface")
    plt.xlabel("Day")
    plt.ylabel("-")
    plt.title("Microbial activity (surface)")
    plt.legend()
    plt.tight_layout()
    path = out_dir / "microbes_activity_surface.png"
    plt.savefig(path, dpi=150)
    print("Saved", path)


def plot_microbes_diagnostics(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
    *,
    pattern: str = "constant",
) -> None:
    # Simple composition diagnostic using final day
    _ensure_out(out_dir)
    orch = build_full_from_preset(profile)
    bus = orch.event_bus
    latest_c: float = 0.0
    latest_n: float = 0.0
    totals_by_group: dict[str, float] = {}

    def _on_snapshot(ev: MicrobialSnapshot) -> None:
        nonlocal latest_c, latest_n
        latest_c = float(ev.total_c_kg_ha)
        latest_n = float(ev.total_n_kg_ha)

    def _on_totals(ev: EnzymeGroupTotals) -> None:
        totals_by_group.update(ev.totals_c_kg_ha_by_group)

    bus.subscribe(MicrobialSnapshot, _on_snapshot)
    bus.subscribe(EnzymeGroupTotals, _on_totals)
    rains, evaps = generate_rain_evap(days, 2.0, 2.0, pattern)
    tmins, tmaxs, pars = generate_temp_par(days, 12.0, 24.0, 10.0, pattern)
    for i in range(days):
        orch.step_day(
            drivers=DailyDrivers(rainfall_mm=rains[i], evaporation_mm=evaps[i]),
            tmin_c=tmins[i],
            tmax_c=tmaxs[i],
            par_mj_m2=pars[i],
        )
    parts = {
        "Microbial C": latest_c,
        "Microbial N": latest_n,
        "Enzyme cost": sum(totals_by_group.values()) or 0.0,
    }
    plt.figure(figsize=(6, 6))
    plt.pie(list(parts.values()), labels=list(parts.keys()), autopct="%1.1f%%")
    plt.title("Microbes diagnostics")
    path = out_dir / "microbes_diagnostics.png"
    plt.savefig(path, dpi=150)
    print("Saved", path)


def generate_microbes_suite(
    out_dir: Path,
    profile: str = "loam_temperate",
    days: int = 120,
) -> None:
    plot_microbes_timeseries(out_dir, profile, days)
    plot_microbes_depth(out_dir, profile, days)
    plot_microbes_split(out_dir, profile, days)
    plot_microbes_enzyme_depth(out_dir, profile, days)
    plot_microbes_activity_depth(out_dir, profile, days)
    plot_microbes_diagnostics(out_dir, profile, days)
    plot_microbes_activity_surface(out_dir, profile, days)
    print("Microbes visualization suite generated in", out_dir)
