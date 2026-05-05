from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Sequence

import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

from agrogame.events.recorder import EventRecorder
from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather.module import WeatherModule
from agrogame.weather.utils import sanitize_weather_series
from agrogame.weather.cli import get_weather_series
from agrogame.atmosphere.et.ports import (
    WaterProfile as ETWaterProfile,
    WaterState as ETWaterState,
    WaterActuator as ETWaterActuator,
)


LANES = [
    "Weather",
    "Soil",
    "ET",
    "Plant",
    "Microbes",
    "Nitrogen",
    "Root",
    "Canopy",
    "Phosphorus",
    "Chemistry",
]


_ET_KEYWORD_LANES: list[tuple[tuple[str, ...], str]] = [
    (("water", "soil"), "Soil"),
    (("evap", "transpir"), "ET"),
    (("nitrogen", "n_", "no3"), "Nitrogen"),
    (("microbial",), "Microbes"),
    (("phosph",), "Phosphorus"),
    (("soilph",), "Chemistry"),
    (("root",), "Root"),
    (("canopy", "lai", "biomass"), "Canopy"),
]

_MN_KEYWORD_LANES: list[tuple[str, str]] = [
    ("agrogame.soil.nitrogen", "Nitrogen"),
    ("agrogame.soil.microbes", "Microbes"),
    ("agrogame.soil.phosphorus", "Phosphorus"),
    ("agrogame.soil.chemistry", "Chemistry"),
]


def _match_from_module_name(mn: str) -> str | None:
    for prefix, lane in _MN_KEYWORD_LANES:
        if prefix in mn:
            return lane
    return None


def _match_event_type(et: str) -> str | None:
    for keywords, lane in _ET_KEYWORD_LANES:
        if any(kw in et for kw in keywords):
            return lane
    return None


def bucket(event_type: str, module_name: str = "") -> str:
    et = event_type.lower()
    if "weather" in et:
        return "Weather"
    et_match = _match_event_type(et)
    if et_match is not None:
        return et_match
    mn = module_name.lower()
    if mn:
        return _match_from_module_name(mn) or (
            "Chemistry" if "chemistry" in mn else "Plant"
        )
    return "Plant"


def _parse_filter_sets(
    include: str, exclude: str, grep: str
) -> tuple[set[str], set[str], str]:
    inc = {s.strip() for s in include.split(",") if s.strip()}
    exc = {s.strip() for s in exclude.split(",") if s.strip()}
    grep_l = (grep or "").lower()
    return inc, exc, grep_l


def _allow_event(ev: Any, inc: set[str], exc: set[str], grep_l: str) -> bool:
    lane = bucket(ev.event_type, ev.module_name)
    passes_include = not inc or lane in inc
    passes_exclude = lane not in exc
    passes_grep = not grep_l or grep_l in ev.event_type.lower()
    return passes_include and passes_exclude and passes_grep


def _filter_events(
    events: Sequence[Any], include: str, exclude: str, grep: str
) -> list:
    inc, exc, grep_l = _parse_filter_sets(include, exclude, grep)
    return [ev for ev in events if _allow_event(ev, inc, exc, grep_l)]


@dataclass
class EventRunConfig:
    days: int
    profile: str = "loam_temperate"


def _day_weather_from_series(
    series: Any, day: int
) -> tuple[float, float, float, float]:
    """Extract (tmin, tmax, rad, rain) from weather series for a given day."""
    w = series.records[day]
    return w.tmin_c, w.tmax_c, (w.net_radiation_mj_m2 or 12.0), (w.precip_mm or 0.0)


def simulate_and_record(
    days: int, profile_key: str, weather_args: Any
) -> tuple[EventRecorder, int]:
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils[profile_key]
    orch = FullSimulationOrchestrator(profile)
    rec = EventRecorder(orch.event_bus)

    series = get_weather_series(weather_args, days)
    if series is not None:
        series = sanitize_weather_series(series)
        total = min(days, len(series.records))
    else:
        total = days
    weather_module = (
        WeatherModule(series, orch.event_bus) if series is not None else None
    )

    for day in range(total):
        rec.set_day(day + 1)
        if series is not None:
            tmin, tmax, rad, rain = _day_weather_from_series(series, day)
            if weather_module is not None:
                _ = weather_module.emit_for_day(day)
        else:
            tmin, tmax, rad, rain = 10.0, 22.0, 12.0, 0.0
        orch.step_day(
            drivers=DailyDrivers(
                rainfall_mm=rain, irrigation_mm=0.0, evaporation_mm=0.0
            ),
            tmin_c=tmin,
            tmax_c=tmax,
            par_mj_m2=rad,
            target_ph=6.8,
        )
    return rec, total


def plot_timeline(
    days: int,
    out: Path,
    weather_args: Any,
    include: str = "",
    exclude: str = "",
    grep: str = "",
) -> None:
    rec, total = simulate_and_record(days, "loam_temperate", weather_args)
    lane_y: dict[str, int] = {name: i for i, name in enumerate(LANES)}
    colors = {
        "Weather": "#1f77b4",
        "Soil": "#17becf",
        "ET": "#2ca02c",
        "Plant": "#bcbd22",
        "Microbes": "#7f7f7f",
        "Nitrogen": "#8c564b",
        "Root": "#9467bd",
        "Canopy": "#ff7f0e",
        "Phosphorus": "#e377c2",
        "Chemistry": "#d62728",
    }
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    ax.set_yticks(range(len(LANES)))
    ax.set_yticklabels(LANES)
    ax.set_xlabel("Day")
    ax.set_title("Event timeline (daily swimlanes)")
    filtered = _filter_events(rec.events, include, exclude, grep)
    for ev in filtered:
        x = ev.day_index or 1
        lane = bucket(ev.event_type, ev.module_name)
        y = lane_y[lane]
        ax.plot(x, y, marker="|", color=colors[lane], markersize=8, linestyle="None")
    ax.set_xlim(1, total)
    ax.set_ylim(-0.5, len(LANES) - 0.5)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)


def plot_heatmap(
    days: int,
    out: Path,
    weather_args: Any,
    include: str = "",
    exclude: str = "",
    grep: str = "",
) -> list[list[int]]:
    rec, total = simulate_and_record(days, "loam_temperate", weather_args)
    row_index = {n: i for i, n in enumerate(LANES)}
    mat: list[list[int]] = [[0 for _ in range(total)] for _ in range(len(LANES))]
    filtered = _filter_events(rec.events, include, exclude, grep)
    for ev in filtered:
        r = row_index.get(bucket(ev.event_type, ev.module_name))
        c_idx = (ev.day_index or 1) - 1
        if r is not None and 0 <= r < len(LANES) and 0 <= c_idx < total:
            mat[r][c_idx] += 1
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(12, 4), constrained_layout=True)
    im = ax.imshow(mat, aspect="auto", cmap="YlOrRd")
    ax.set_yticks(range(len(LANES)))
    ax.set_yticklabels(LANES)
    ax.set_xlabel("Day")
    ax.set_title("Event density by module (daily)")
    fig.colorbar(im, ax=ax, label="Events/day")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    return mat


def _setup_dependency_modules(
    fc_scale: float,
) -> tuple:
    """Set up all simulation modules for dependency plotting."""
    from agrogame.events import EventBus
    from agrogame.events.recorder import EventRecorder
    from agrogame.soil.phenology import (
        CropPhenologyParams,
        GrowthStageThresholds,
        PhenologyModule,
    )
    from agrogame.soil.canopy import CanopyModule, CanopyParams
    from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
    from agrogame.soil.water.state import SoilWaterState
    from agrogame.soil.nitrogen import SoilNitrogenState
    from agrogame.soil.nitrogen.cycle import NitrogenCycle
    from agrogame.plant.roots import RootModule, RootParams, RootState
    from agrogame.atmosphere.et import Evapotranspiration, EtParams
    from agrogame.soil.canopy.interception import InterceptionState

    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    base = soil_lib.soils["loam_temperate"]
    new_layers = []
    for lyr in base.layers:
        wp, fc, sat = lyr.wilting_point, lyr.field_capacity, lyr.saturation
        nfc = max(wp + 0.005, min(sat - 0.005, fc * fc_scale))
        new_layers.append(lyr.model_copy(update={"field_capacity": float(nfc)}))
    profile = base.model_copy(update={"layers": new_layers})

    bus = EventBus()
    rec = EventRecorder(bus)
    phen = PhenologyModule(
        CropPhenologyParams(
            base_temperature_c=8.0,
            max_temperature_c=35.0,
            thresholds=GrowthStageThresholds(
                emergence_gdd=100.0, flowering_gdd=900.0, maturity_gdd=1700.0
            ),
        ),
        event_bus=bus,
    )
    canopy = CanopyModule(
        CanopyParams(
            extinction_coefficient_k=0.6,
            radiation_use_efficiency_g_per_mj=3.0,
            specific_leaf_area_m2_per_g=0.02,
            lai_max=6.0,
            senescence_rate_per_day=0.01,
        ),
        event_bus=bus,
    )
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(bus, nstate)
    roots = RootModule(RootParams(), event_bus=bus)
    rstate = RootState()
    etmod = Evapotranspiration(EtParams())
    istate = InterceptionState()

    return (
        profile,
        bus,
        rec,
        phen,
        canopy,
        water,
        wstate,
        ncycle,
        roots,
        rstate,
        etmod,
        istate,
    )


def _run_dependency_sim(
    days: int,
    weather_args: Any,
    profile: Any,
    bus: Any,
    rec: Any,
    phen: Any,
    canopy: Any,
    water: Any,
    wstate: Any,
    ncycle: Any,
    roots: Any,
    rstate: Any,
    etmod: Any,
    istate: Any,
) -> int:
    """Run the dependency simulation loop and return total days."""
    from typing import cast

    series = get_weather_series(weather_args, days)
    if series is not None:
        series = sanitize_weather_series(series)
        total = min(days, len(series.records))
    else:
        total = days
    weather_module = WeatherModule(series, bus) if series is not None else None

    for day in range(total):
        rec.set_day(day + 1)
        if series is not None:
            w = series.records[day]
            if weather_module is not None:
                _ = weather_module.emit_for_day(day)
            tmin, tmax, rad = w.tmin_c, w.tmax_c, (w.net_radiation_mj_m2 or 12.0)
            rain = w.precip_mm or 0.0
        else:
            tmin, tmax, rad, rain = 10.0, 22.0, 12.0, 0.0
        phen.update_daily(tmin_c=tmin, tmax_c=tmax, photoperiod_h=12.0)
        _ = canopy.daily_step(
            incident_par_mj_m2=rad, temp_factor=1.0, water_stress=1.0, n_stress=1.0
        )
        _ = roots.daily_step(rstate, profile, phen.state.stage)
        root_fracs = (
            tuple(rstate.layer_fractions)
            if rstate.layer_fractions is not None
            else tuple([1.0 / len(profile.layers)] * len(profile.layers))
        )
        intercepted, throughfall = istate.intercept(canopy.state.lai, rain)
        _ = water.update_daily(
            profile, wstate, DailyDrivers(rainfall_mm=throughfall, evaporation_mm=0.0)
        )
        et0 = etmod.priestley_taylor(
            temp_mean_c=0.5 * (tmin + tmax), net_radiation_mj_m2=rad
        )
        comps = etmod.potential_components(et0_mm=et0, lai=canopy.state.lai)

        _ = etmod.actual_et(
            cast(ETWaterProfile, profile),
            cast(ETWaterState, wstate),
            cast(ETWaterActuator, water),
            comps,
            root_fracs,
        )
        _ = ncycle.daily_step(temperature_c=0.5 * (tmin + tmax), plant_demand_kg_ha=1.0)

    return total


def _build_edges(rec: Any) -> dict[tuple[str, str], int]:
    """Build chronological edges per day across bucketed modules."""
    edges: dict[tuple[str, str], int] = {}
    day_events: dict[int, list] = {}
    for ev in rec.events:
        day_events.setdefault(ev.day_index or 0, []).append(ev)
    from itertools import pairwise

    for _, evs in day_events.items():
        modules = [bucket(e.event_type, e.module_name) for e in evs]
        for a, b in pairwise(modules):
            if a != b:
                edges[(a, b)] = edges.get((a, b), 0) + 1
    return edges


def _draw_dependency_graph(edges: dict[tuple[str, str], int], out: Path) -> None:
    """Draw and save the dependency graph."""
    import math

    nodes = list(LANES)
    n_nodes = len(nodes)
    angles = [2 * math.pi * i / n_nodes for i in range(n_nodes)]
    pos = {nodes[i]: (math.cos(ang), math.sin(ang)) for i, ang in enumerate(angles)}
    plt.style.use("ggplot")
    fig, ax = plt.subplots(figsize=(10, 10), constrained_layout=True)
    for name, (x, y) in pos.items():
        ax.plot(x, y, "o", color="#1f77b4", markersize=18, zorder=3)
        txt = ax.text(
            x,
            y,
            name,
            ha="center",
            va="center",
            fontsize=13,
            color="black",
            weight="bold",
            zorder=4,
        )
        txt.set_path_effects([pe.withStroke(linewidth=3, foreground="white")])
    max_cnt = max(edges.values()) if edges else 1
    for (a, b), cnt in edges.items():
        x1, y1 = pos[a]
        x2, y2 = pos[b]
        lw = 0.6 + 4.0 * (cnt / max_cnt) ** 0.7
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={
                "arrowstyle": "->",
                "lw": lw,
                "color": "#d62728",
                "alpha": 0.65,
                "shrinkA": 12,
                "shrinkB": 12,
                "connectionstyle": "arc3,rad=0.25",
            },
        )
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Event dependency (bucketed, same-day transitions)")
    ax.set_aspect("equal")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180)


def plot_dependencies(days: int, out: Path, fc_scale: float, weather_args: Any) -> None:
    (
        profile,
        bus,
        rec,
        phen,
        canopy,
        water,
        wstate,
        ncycle,
        roots,
        rstate,
        etmod,
        istate,
    ) = _setup_dependency_modules(fc_scale)
    _run_dependency_sim(
        days,
        weather_args,
        profile,
        bus,
        rec,
        phen,
        canopy,
        water,
        wstate,
        ncycle,
        roots,
        rstate,
        etmod,
        istate,
    )
    edges = _build_edges(rec)
    _draw_dependency_graph(edges, out)
