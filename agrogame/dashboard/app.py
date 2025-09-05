from __future__ import annotations
from pathlib import Path
from datetime import timedelta
from typing import Optional, Any, Dict, Mapping, NamedTuple
import math
import time
from io import StringIO

import plotly.graph_objects as go
import streamlit as st

from agrogame.sim.orchestrator import FullSimulationOrchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather
from agrogame.weather.utils import vpd_kpa
from agrogame.weather.types import WeatherRecord
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phenology.types import PhenologyStage
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.soil.models import SoilProfile
from agrogame.soil.water.events import EvaporationTaken, TranspirationByLayer


def _extend_weather_records(
    records: list[WeatherRecord], days: int
) -> list[WeatherRecord]:
    """Extend records by cycling existing days to reach requested length.

    This keeps the original ordering and increments the day field sequentially.
    """
    if days <= len(records) or not records:
        return records
    out = list(records)
    last_day = out[-1].day
    base = list(records)
    k = 0
    while len(out) < days:
        tmpl = base[k % len(base)]
        k += 1
        last_day = last_day + timedelta(days=1)
        out.append(
            WeatherRecord(
                day=last_day,
                tmin_c=tmpl.tmin_c,
                tmax_c=tmpl.tmax_c,
                relative_humidity_pct=tmpl.relative_humidity_pct,
                wind_m_s=tmpl.wind_m_s,
                shortwave_mj_m2=tmpl.shortwave_mj_m2,
                net_radiation_mj_m2=tmpl.net_radiation_mj_m2,
                albedo=tmpl.albedo,
                precip_mm=tmpl.precip_mm,
            )
        )
    return out


def _apply_fertilizers(
    ncycle: NitrogenCycle,
    i: int,
    fert_ops: list[tuple[int, float, str, int]] | None,
    fert_map: Mapping[int, float] | None,
) -> None:
    """Apply fertilizer operations for the current day index.

    Supports the detailed ops (type + layer) or a backward-compatible map.
    """
    if fert_ops:
        for d, amt, ftype, layer_idx in fert_ops:
            if d == i and amt > 0.0:
                if ftype == "urea":
                    ncycle.apply_urea(layer=layer_idx, amount_kg_ha=amt)
                else:
                    ncycle.apply_ammonium_nitrate(layer=layer_idx, amount_kg_ha=amt)
        return
    if fert_map:
        amt_simple = float(fert_map.get(i, 0.0))
        if amt_simple > 0.0:
            ncycle.apply_ammonium_nitrate(layer=0, amount_kg_ha=amt_simple)


def _compute_reference_et(
    et_mod: Evapotranspiration,
    rec: WeatherRecord,
) -> tuple[float, Optional[float], float, float, float, float]:
    """Compute ET0 (PM, PT), VPD and thermal/energy inputs used downstream.

    Returns (et0_pm, et0_pt, par, rn, tmean, vpd).
    """
    par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
    rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
    tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
    et0_pm = et_mod.et0(
        temp_mean_c=tmean,
        net_radiation_mj_m2=rn,
        method="penman-monteith",
        wind_m_s=rec.wind_m_s or 2.0,
        relative_humidity_pct=rec.relative_humidity_pct or 60.0,
    )
    try:
        et0_pt = et_mod.priestley_taylor(temp_mean_c=tmean, net_radiation_mj_m2=rn)
    except Exception:
        et0_pt = None
    vpd = vpd_kpa(tmean, rec.relative_humidity_pct or 60.0)
    return et0_pm, et0_pt, par, rn, tmean, vpd


# Removed legacy ET partition helper; actual ET is captured via events


def _init_orchestrator(
    profile: SoilProfile,
) -> tuple[FullSimulationOrchestrator, Evapotranspiration]:
    """Build a full orchestrator and ET helper for diagnostics."""
    orch = FullSimulationOrchestrator(profile)
    et_mod = Evapotranspiration(EtParams())
    return orch, et_mod


def _new_history(profile: SoilProfile) -> Dict[str, Any]:
    """Allocate the history structure for time series outputs."""
    return {
        "day": [],
        "lai": [],
        "biomass_g_m2": [],
        "biomass_inc_g_m2": [],
        "theta_layers": [[] for _ in profile.layers],
        "no3_layers": [[] for _ in profile.layers],
        "nh4_layers": [[] for _ in profile.layers],
        "root_depth_cm": [],
        "stage": [],
        "gdd_accum": [],
        "rain_mm": [],
        "tmin_c": [],
        "tmax_c": [],
        "tmean_c": [],
        "par_mj_m2": [],
        "par_intercepted_mj_m2": [],
        "fraction_intercepted": [],
        "et0_mm": [],
        "et0_pt_mm": [],
        "evap_mm": [],
        "transp_mm": [],
        "vpd_kpa": [],
        "stomatal": [],
        "water_stress": [],
        "n_total_kgha": [],
        # phenology thresholds (for progress bar)
        "thr_emergence": None,
        "thr_flowering": None,
        "thr_maturity": None,
    }


def _run_simulation(
    days: int,
    weather_file: Path,
    irrigation_schedule: list[tuple[int, float]] | None = None,
    fertilizer_schedule: list[tuple[int, float]] | None = None,
    *,
    fertilizer_ops: list[tuple[int, float, str, int]] | None = None,
) -> tuple[Dict[str, Any], SoilProfile]:
    soil_lib = load_soil_presets(Path("data/soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]
    orch, et_mod = _init_orchestrator(profile)

    weather = load_weather(weather_file)
    records: list[WeatherRecord] = _extend_weather_records(list(weather.records), days)

    history: Dict[str, Any] = _new_history(profile)

    irrig_map = dict(irrigation_schedule or [])
    fert_map = dict(fertilizer_schedule or [])
    fert_ops = list(fertilizer_ops or [])

    # Capture phenology thresholds once for progress computation
    try:
        thr = orch.phenology.params.thresholds
        history["thr_emergence"] = thr.emergence_gdd
        history["thr_flowering"] = thr.flowering_gdd
        history["thr_maturity"] = thr.maturity_gdd
    except Exception:
        pass

    # Subscribe to ET-related events to capture actual evaporation/transpiration
    daily_evap: float = 0.0
    daily_transp: float = 0.0

    def _on_evap(ev: EvaporationTaken) -> None:
        nonlocal daily_evap
        daily_evap += float(ev.amount_mm)

    def _on_transp(ev: TranspirationByLayer) -> None:
        nonlocal daily_transp
        daily_transp += float(getattr(ev, "total_mm", sum(ev.amounts_mm)))

    orch.event_bus.subscribe(EvaporationTaken, _on_evap)
    orch.event_bus.subscribe(TranspirationByLayer, _on_transp)

    for i in range(min(days, len(records))):
        rec = records[i]
        rain = rec.precip_mm or 0.0
        irrigation = irrig_map.get(i, 0.0)

        _apply_fertilizers(orch.n_cycle, i, fert_ops, fert_map)

        et0, et0_pt, par, rn, tmean, vpd = _compute_reference_et(et_mod, rec)
        history["et0_mm"].append(et0)
        history["et0_pt_mm"].append(et0_pt)

        # Reset daily ET counters and advance one day via Calendar/DayTick
        daily_evap = 0.0
        daily_transp = 0.0
        drivers = DailyDrivers(
            rainfall_mm=rain + irrigation,
            irrigation_mm=0.0,
            evaporation_mm=0.0,
        )
        orch.step_day(
            drivers=drivers,
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
        )

        # Derive water stress and stomatal proxy
        comps = et_mod.potential_components_with_vpd(
            et0_mm=et0, lai=orch.canopy.state.lai, vpd_kpa=vpd
        )
        demand = max(1e-6, comps.potential_transp_mm)
        water_stress = max(0.05, min(1.0, daily_transp / demand))
        vpd_excess = max(0.0, vpd - et_mod.params.vpd_ref_kpa)
        stomatal = max(0.2, 1.0 - et_mod.params.vpd_sensitivity * vpd_excess)
        history["evap_mm"].append(float(daily_evap))
        history["transp_mm"].append(float(daily_transp))
        history["water_stress"].append(water_stress)
        history["vpd_kpa"].append(vpd)
        history["stomatal"].append(stomatal)

        # Nitrogen status proxy now reflects orchestrator-run cycles

        history["day"].append(rec.day)
        history["lai"].append(orch.canopy.state.lai)
        # Biomass and increment
        current_biomass = orch.canopy.state.biomass_g_m2
        prev_biomass = history["biomass_g_m2"][-1] if history["biomass_g_m2"] else 0.0
        history["biomass_g_m2"].append(current_biomass)
        history["biomass_inc_g_m2"].append(max(0.0, current_biomass - prev_biomass))
        # PAR and interception (Beer–Lambert)
        try:
            k_ext = float(getattr(orch.canopy.params, "extinction_coefficient_k", 0.6))
        except Exception:
            k_ext = 0.6
        lai_now2 = float(orch.canopy.state.lai or 0.0)
        frac_int = (
            0.0
            if lai_now2 <= 0.0 or par <= 0.0
            else (1.0 - math.exp(-k_ext * lai_now2))
        )
        history["par_mj_m2"].append(par)
        history["fraction_intercepted"].append(frac_int)
        history["par_intercepted_mj_m2"].append(par * frac_int)
        # Root depth and phenology stage
        try:
            history["root_depth_cm"].append(orch.root_state.current_depth_cm)
        except Exception:
            history["root_depth_cm"].append(0.0)
        stage = getattr(getattr(orch.phenology, "state", None), "stage", None)
        history["stage"].append(
            stage.value if isinstance(stage, PhenologyStage) else str(stage)
        )
        # Accumulated GDD for progress bar
        try:
            history["gdd_accum"].append(
                getattr(orch.phenology.state, "accumulated_gdd", None)
            )
        except Exception:
            history["gdd_accum"].append(None)
        for li, _layer in enumerate(profile.layers):
            # store volumetric water content per layer
            if len(history["theta_layers"][li]) == i:
                history["theta_layers"][li].append(orch.water_state.theta[li])
            else:
                history["theta_layers"][li][i] = orch.water_state.theta[li]
            # nitrogen pools
            if len(history["no3_layers"][li]) == i:
                history["no3_layers"][li].append(orch.n_state.no3[li])
                history["nh4_layers"][li].append(orch.n_state.nh4[li])
            else:
                history["no3_layers"][li][i] = orch.n_state.no3[li]
                history["nh4_layers"][li][i] = orch.n_state.nh4[li]
        history["rain_mm"].append(rain)
        history["tmin_c"].append(rec.tmin_c)
        history["tmax_c"].append(rec.tmax_c)
        history["tmean_c"].append(tmean)
        # Aggregate N status proxy (total mineral N across layers)
        history["n_total_kgha"].append(sum(orch.n_state.no3) + sum(orch.n_state.nh4))

    return history, profile


class SidebarConfig(NamedTuple):
    weather_path: str
    days: int
    high_contrast: bool
    irr_day: int
    irr_mm: float
    fert_day: int
    fert_kgha: float
    fert_type: str
    fert_layer: int
    autorun: bool
    run: bool


def _read_autorun_default() -> bool:
    """Read query parameter autorun to determine default auto-run behavior."""
    autorun_param = "0"
    try:
        autorun_param = str(getattr(st, "query_params", {}).get("autorun", "0"))
    except Exception:
        try:
            autorun_param = st.experimental_get_query_params().get("autorun", ["0"])[0]
        except Exception:
            autorun_param = "0"
    return autorun_param == "1"


def _collect_sidebar_inputs() -> SidebarConfig:
    """Render sidebar controls and return collected configuration."""
    st.sidebar.header("Scenario")
    weather_path = st.sidebar.text_input(
        "Weather file", value=str(Path("data/weather/sample.csv").resolve())
    )
    days = int(st.sidebar.number_input("Days", min_value=10, max_value=365, value=120))
    st.sidebar.header("Display")
    high_contrast = bool(st.sidebar.checkbox("High-contrast mode", value=False))
    st.sidebar.header("Management (optional)")
    irr_day = int(st.sidebar.number_input("Irrigation day index", min_value=0, value=0))
    irr_mm = float(
        st.sidebar.number_input("Irrigation amount (mm)", min_value=0.0, value=0.0)
    )
    fert_day = int(
        st.sidebar.number_input("Fertilizer day index", min_value=0, value=0)
    )
    fert_kgha = float(
        st.sidebar.number_input("Fertilizer amount (kg N/ha)", min_value=0.0, value=0.0)
    )
    fert_type = str(
        st.sidebar.selectbox("Fertilizer type", ["ammonium_nitrate", "urea"])
    )
    fert_layer = int(
        st.sidebar.number_input("Fertilizer layer index", min_value=0, value=0)
    )
    autorun_default = _read_autorun_default()
    autorun = bool(
        st.sidebar.checkbox("Auto-run on load", value=autorun_default or True)
    )
    run = bool(st.sidebar.button("Run Simulation") or autorun)
    return SidebarConfig(
        weather_path,
        days,
        high_contrast,
        irr_day,
        irr_mm,
        fert_day,
        fert_kgha,
        fert_type,
        fert_layer,
        autorun,
        run,
    )


def _set_global_day_slider(history: Mapping[str, Any]) -> int:
    """Create the global day slider and return the selected index (1..N)."""
    st.session_state.setdefault("_days_cache", [])
    st.session_state["_days_cache"] = history.get("day", [])
    gmax = len(history.get("day", [])) or 1
    return int(
        st.slider(
            "Day",
            min_value=1,
            max_value=gmax,
            value=gmax,
            key="global_day_slider",
        )
    )


def _render_all_tabs(
    history: Mapping[str, Any],
    profile: SoilProfile,
    high_contrast: bool,
    irrigation_schedule: list[tuple[int, float]],
    fertilizer_schedule: list[tuple[int, float]],
) -> None:
    tab1, tab2, tab3, tab4 = st.tabs(["Soil", "Crop", "Management", "Weather"])
    upto = (
        None
        if "global_idx" not in st.session_state
        else int(st.session_state["global_idx"])
    )
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Soil moisture by layer")
            _plot_soil_moisture(
                history, profile, upto_idx=upto, high_contrast=high_contrast
            )
        with col2:
            st.subheader("Soil nitrogen by layer")
            _plot_nitrogen(history, profile, upto_idx=upto)

    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Biomass accumulation")
            _plot_biomass(history, upto_idx=upto)
            # Yield projection with simple CI
            try:
                biomass = float(history["biomass_g_m2"][-1])
                harvest_index = 0.5
                yield_tha = (biomass / 100.0) * harvest_index
                lo = yield_tha * 0.8
                hi = yield_tha * 1.2
                st.metric(
                    "Yield projection (t/ha)",
                    f"{yield_tha:.1f}",
                    help=f"80%–120% CI: {lo:.1f}–{hi:.1f} t/ha",
                )
            except Exception:
                pass
        with c2:
            st.subheader("Root depth")
            _plot_root_depth(history, upto_idx=upto)
            # Root-depth animation (playback to current day)
            play = st.button("Play root animation", key="root_anim_play")
            if play:
                placeholder = st.empty()
                max_i = int(st.session_state.get("global_idx", len(history["day"])))
                for frame in range(1, max_i + 1):
                    with placeholder.container():
                        _plot_root_depth(history, upto_idx=frame)
                    time.sleep(0.04)
        st.subheader("Phenology timeline")
        _plot_phenology(history, upto_idx=upto)
        if history.get("stage"):
            st.metric("Phenology stage", history["stage"][-1])
        # Nutrient traffic lights (N modeled, P not modeled yet)
        try:
            n_total = float(history.get("n_total_kgha", [0.0])[-1] or 0.0)
            if n_total >= 120:
                n_badge = "🟢 N sufficient"
            elif n_total >= 60:
                n_badge = "🟡 N moderate"
            else:
                n_badge = "🔴 N low"
            st.markdown(n_badge)
            st.markdown("⚪ P status: N/A (not modeled)")
        except Exception:
            pass
        col3, col4 = st.columns(2)
        with col3:
            st.subheader("Leaf area index (LAI)")
            _plot_lai(history, upto_idx=upto)
        with col4:
            st.subheader("PAR interception")
            _plot_interception(history, upto_idx=upto)

    with tab3:
        st.write("Management actions applied in this run:")
        if irrigation_schedule:
            st.write(
                "Irrigation: day "
                + f"{irrigation_schedule[0][0]}, "
                + f"{irrigation_schedule[0][1]} mm"
            )
        else:
            st.write("Irrigation: none")
        if fertilizer_schedule:
            st.write(
                "Fertilizer (AN): day "
                + f"{fertilizer_schedule[0][0]}, "
                + f"{fertilizer_schedule[0][1]} kg/ha"
            )
        else:
            st.write("Fertilizer: none")

    with tab4:
        w1, w2 = st.columns(2)
        with w1:
            st.subheader("Weather overview")
            _plot_weather(history, upto_idx=upto)
        with w2:
            st.subheader("ET components")
            _plot_et(history, upto_idx=upto)
        st.subheader("VPD and stomatal factor")
        _plot_vpd_stomatal(history, upto_idx=upto)


def _gradient_hex(color_a: str, color_b: str, steps: int) -> list[str]:
    def to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def to_hex(rgb: tuple[int, int, int]) -> str:
        return "#%02x%02x%02x" % rgb

    ra, ga, ba = to_rgb(color_a)
    rb, gb, bb = to_rgb(color_b)
    out: list[str] = []
    for i in range(max(1, steps)):
        t = 0 if steps == 1 else i / (steps - 1)
        r = int(ra + (rb - ra) * t)
        g = int(ga + (gb - ga) * t)
        b = int(ba + (bb - ba) * t)
        out.append(to_hex((r, g, b)))
    return out


def _plot_soil_moisture(
    history: Mapping[str, Any],
    profile: SoilProfile,
    *,
    upto_idx: int | None = None,
    high_contrast: bool = False,
) -> None:
    fig = go.Figure()
    # Blue → brown gradient per layer (high-contrast uses darker tones)
    start = "#08519c" if high_contrast else "#1f77b4"
    end = "#7f2704" if high_contrast else "#8c564b"
    colors = _gradient_hex(start, end, len(profile.layers))
    for i, _layer in enumerate(profile.layers):
        x = history["day"]
        y = history["theta_layers"][i]
        if upto_idx is not None:
            x = x[:upto_idx]
            y = y[:upto_idx]
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=f"Layer {i+1} θ (m³/m³)",
                hovertemplate=f"Layer {i+1} θ: %{{y:.3f}} m³/m³<extra></extra>",
                line={
                    "color": colors[i % len(colors)],
                    "width": 2 if high_contrast else 1.5,
                },
            )
        )
    fig.update_layout(
        yaxis_title="Volumetric water content (m³/m³)",
        template=("plotly_white" if high_contrast else None),
    )
    st.plotly_chart(fig, use_container_width=True)
    # CSV export for soil moisture
    try:
        buf = StringIO()
        # header
        header = ["day"] + [f"theta_layer_{i+1}" for i in range(len(profile.layers))]
        buf.write(",".join(header) + "\n")
        n = len(history["day"]) if upto_idx is None else upto_idx
        for idx in range(n):
            row = [str(history["day"][idx])]
            for li in range(len(profile.layers)):
                row.append(f"{history['theta_layers'][li][idx]:.4f}")
            buf.write(",".join(row) + "\n")
        st.download_button(
            "Download soil moisture CSV",
            data=buf.getvalue(),
            mime="text/csv",
            file_name="soil_moisture_timeseries.csv",
        )
    except Exception:
        pass


def _plot_nitrogen(
    history: Mapping[str, Any], profile: SoilProfile, *, upto_idx: int | None = None
) -> None:
    tabs = st.tabs(["NO3 (kg/ha)", "NH4 (kg/ha)"])
    with tabs[0]:
        fig_no3 = go.Figure()
        for i, _layer in enumerate(profile.layers):
            x = history["day"]
            y = history["no3_layers"][i]
            if upto_idx is not None:
                x = x[:upto_idx]
                y = y[:upto_idx]
            fig_no3.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=f"Layer {i+1} NO3",
                    hovertemplate=f"Layer {i+1} NO3: %{{y:.1f}} kg/ha<extra></extra>",
                )
            )
        fig_no3.update_layout(yaxis_title="NO3 (kg/ha)")
        st.plotly_chart(fig_no3, use_container_width=True)
    with tabs[1]:
        fig_nh4 = go.Figure()
        for i, _layer in enumerate(profile.layers):
            x = history["day"]
            y = history["nh4_layers"][i]
            if upto_idx is not None:
                x = x[:upto_idx]
                y = y[:upto_idx]
            fig_nh4.add_trace(
                go.Scatter(
                    x=x,
                    y=y,
                    mode="lines",
                    name=f"Layer {i+1} NH4",
                    hovertemplate=f"Layer {i+1} NH4: %{{y:.1f}} kg/ha<extra></extra>",
                )
            )
        fig_nh4.update_layout(yaxis_title="NH4 (kg/ha)")
        st.plotly_chart(fig_nh4, use_container_width=True)


def _plot_biomass(history: Mapping[str, Any], *, upto_idx: int | None = None) -> None:
    x = history["day"]
    y = history["biomass_g_m2"]
    if upto_idx is not None:
        x = x[:upto_idx]
        y = y[:upto_idx]
    fig = go.Figure(
        data=[
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                hovertemplate="Biomass: %{{y:.0f}} g m⁻²<extra></extra>",
            )
        ]
    )
    fig.update_layout(yaxis_title="Biomass (g m⁻²)")
    st.plotly_chart(fig, use_container_width=True)
    # CSV export for biomass
    try:
        buf = StringIO()
        n = len(history["day"]) if upto_idx is None else upto_idx
        buf.write("day,biomass_g_m2\n")
        for i in range(n):
            buf.write(f"{history['day'][i]},{history['biomass_g_m2'][i]:.2f}\n")
        st.download_button(
            "Download biomass CSV",
            data=buf.getvalue(),
            mime="text/csv",
            file_name="biomass_timeseries.csv",
        )
    except Exception:
        pass
    if history.get("water_stress"):
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Water stress", f"{history['water_stress'][-1]:.2f}")
        with c2:
            n_total = history.get("n_total_kgha", [0])[-1]
            n_target = 150.0
            n_stress = max(0.0, min(1.0, (n_total or 0.0) / n_target))
            st.metric("N stress (proxy)", f"{n_stress:.2f}")
        with c3:
            tmean = history.get("tmean_c", [None])[-1]
            if tmean is not None:
                optimal = 20.0
                range_c = 15.0
                temp_stress = max(0.0, 1.0 - abs(tmean - optimal) / range_c)
                st.metric("Temp stress (proxy)", f"{temp_stress:.2f}")


def _plot_root_depth(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> None:
    x = history["day"]
    y = history["root_depth_cm"]
    if upto_idx is not None:
        x = x[:upto_idx]
        y = y[:upto_idx]
    fig = go.Figure(data=[go.Scatter(x=x, y=y, mode="lines")])
    fig.update_layout(yaxis_title="Root depth (cm)")
    st.plotly_chart(fig, use_container_width=True)
    # CSV export for root depth
    try:
        buf = StringIO()
        n = len(history["day"]) if upto_idx is None else upto_idx
        buf.write("day,root_depth_cm\n")
        for i in range(n):
            buf.write(f"{history['day'][i]},{history['root_depth_cm'][i]:.2f}\n")
        st.download_button(
            "Download root depth CSV",
            data=buf.getvalue(),
            mime="text/csv",
            file_name="root_depth_timeseries.csv",
        )
    except Exception:
        pass


def _plot_lai(history: Mapping[str, Any], *, upto_idx: int | None = None) -> None:
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    lai = (
        history.get("lai", [])
        if upto_idx is None
        else history.get("lai", [])[:upto_idx]
    )
    fig = go.Figure(data=[go.Scatter(x=x, y=lai, mode="lines", name="LAI")])
    fig.update_layout(yaxis_title="LAI (-)")
    st.plotly_chart(fig, use_container_width=True)


def _plot_interception(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> None:
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    par = (
        history.get("par_mj_m2", [])
        if upto_idx is None
        else history.get("par_mj_m2", [])[:upto_idx]
    )
    par_int = (
        history.get("par_intercepted_mj_m2", [])
        if upto_idx is None
        else history.get("par_intercepted_mj_m2", [])[:upto_idx]
    )
    frac = (
        history.get("fraction_intercepted", [])
        if upto_idx is None
        else history.get("fraction_intercepted", [])[:upto_idx]
    )
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=x, y=par, mode="lines", name="PAR (MJ m⁻²)", yaxis="y1"))
    fig.add_trace(
        go.Scatter(
            x=x, y=par_int, mode="lines", name="Intercepted PAR (MJ m⁻²)", yaxis="y1"
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x, y=frac, mode="lines", name="Fraction intercepted (-)", yaxis="y2"
        )
    )
    fig.update_layout(
        yaxis={"title": "PAR (MJ m⁻²)", "side": "left"},
        yaxis2={
            "title": "Fraction (-)",
            "overlaying": "y",
            "side": "right",
            "rangemode": "tozero",
        },
    )
    st.plotly_chart(fig, use_container_width=True)


def _plot_phenology(history: Mapping[str, Any], *, upto_idx: int | None = None) -> None:
    stages_full = [str(s) for s in history.get("stage", [])]
    stages = stages_full if upto_idx is None else stages_full[:upto_idx]
    if not stages:
        st.info("No phenology data available.")
        return

    # Build contiguous segments (stage, duration_in_days)
    segments: list[tuple[str, int]] = []
    current = stages[0]
    start_idx = 0
    for i, s in enumerate(stages[1:], start=1):
        if s != current:
            segments.append((current, i - start_idx))
            current = s
            start_idx = i
    segments.append((current, len(stages) - start_idx))

    # Colors inspired by plot_full_integration.py
    color_map: dict[str, str] = {
        "planted": "#9ecae1",
        "emerged": "#a1d99b",
        "vegetative": "#74c476",
        "flowering": "#fd8d3c",
        "grain_fill": "#fdd0a2",
        "maturity": "#bcbddc",
    }

    fig = go.Figure()
    for name, duration in segments:
        fig.add_trace(
            go.Bar(
                x=[max(1, int(duration))],
                y=["Stage"],
                orientation="h",
                marker_color=color_map.get(name, "#6272a4"),
                name=name,
                text=[name],
                textposition="inside",
                hovertemplate="%{text} · %{x} days<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack",
        xaxis_title="Day",
        yaxis={"visible": False, "showticklabels": False},
        showlegend=True,
        height=140,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    st.plotly_chart(fig, use_container_width=True)
    # Progress bar based on accumulated GDD vs thresholds
    last_stage = (history.get("stage", []) or [None])[-1]
    last_gdd = (history.get("gdd_accum", []) or [None])[-1]
    te = history.get("thr_emergence") or 0.0
    tf = history.get("thr_flowering") or te
    tm = history.get("thr_maturity") or tf
    frac = None
    if last_gdd is not None and isinstance(last_stage, str):
        s = last_stage
        if s == "planted":
            denom = max(1e-6, te)
            frac = max(0.0, min(1.0, last_gdd / denom))
        elif s == "vegetative":
            denom = max(1e-6, tf - te)
            frac = max(0.0, min(1.0, (last_gdd - te) / denom))
        elif s == "grain_fill":
            denom = max(1e-6, tm - tf)
            frac = max(0.0, min(1.0, (last_gdd - tf) / denom))
        elif s in ("emerged", "flowering", "maturity"):
            frac = 1.0
    if frac is not None:
        st.progress(frac, text=f"Stage {last_stage}: {int(frac*100)}%")


def _plot_weather(history: Mapping[str, Any], *, upto_idx: int | None = None) -> None:
    fig = go.Figure()
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    tmin = history["tmin_c"] if upto_idx is None else history["tmin_c"][:upto_idx]
    tmax = history["tmax_c"] if upto_idx is None else history["tmax_c"][:upto_idx]
    rain = history["rain_mm"] if upto_idx is None else history["rain_mm"][:upto_idx]
    et0 = history["et0_mm"] if upto_idx is None else history["et0_mm"][:upto_idx]
    fig.add_trace(go.Scatter(x=x, y=tmin, mode="lines", name="Tmin"))
    fig.add_trace(go.Scatter(x=x, y=tmax, mode="lines", name="Tmax"))
    fig.add_trace(go.Bar(x=x, y=rain, name="Rain (mm)", opacity=0.4))
    fig.add_trace(go.Scatter(x=x, y=et0, mode="lines", name="ET0 PM"))
    if any(history.get("et0_pt_mm", [])):
        et0pt = (
            history["et0_pt_mm"]
            if upto_idx is None
            else history["et0_pt_mm"][:upto_idx]
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=et0pt,
                mode="lines",
                name="ET0 PT",
            )
        )
    fig.update_layout(yaxis_title="Temp (°C) / Rain & ET0 (mm)")
    st.plotly_chart(fig, use_container_width=True)
    # Headline metrics for last visible day
    try:
        last = -1 if upto_idx is None else upto_idx - 1
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Tmin (°C)", f"{tmin[last]:.1f}")
        with c2:
            st.metric("Tmax (°C)", f"{tmax[last]:.1f}")
        with c3:
            st.metric("Rain (mm)", f"{rain[last]:.1f}")
        with c4:
            st.metric("ET0 (mm)", f"{et0[last]:.1f}")
    except Exception:
        pass
    # Naive 7-day forecast (persistence from recent week)
    try:
        if history.get("day"):
            last_day = history["day"][-1]
            from datetime import timedelta as _td

            # choose recent window
            def recent(seq: list[Any], n: int) -> list[Any]:
                if not seq:
                    return []
                if len(seq) >= n:
                    return list(seq[-n:])
                return [seq[-1]] * n

            tmin_f = recent(history["tmin_c"], 7)
            tmax_f = recent(history["tmax_c"], 7)
            et0_f = recent(history["et0_mm"], 7)
            rain_f = recent(history["rain_mm"], 7)
            days_f = [last_day + _td(days=i + 1) for i in range(7)]
            fig_f = go.Figure()
            fig_f.add_trace(
                go.Scatter(
                    x=days_f,
                    y=tmin_f,
                    mode="lines",
                    name="Tmin (fcst)",
                    line={"dash": "dot"},
                )
            )
            fig_f.add_trace(
                go.Scatter(
                    x=days_f,
                    y=tmax_f,
                    mode="lines",
                    name="Tmax (fcst)",
                    line={"dash": "dot"},
                )
            )
            fig_f.add_trace(go.Bar(x=days_f, y=rain_f, name="Rain (fcst)", opacity=0.3))
            fig_f.add_trace(
                go.Scatter(
                    x=days_f,
                    y=et0_f,
                    mode="lines",
                    name="ET0 PM (fcst)",
                    line={"dash": "dot"},
                )
            )
            fig_f.update_layout(yaxis_title="Forecast: Temp (°C) / Rain & ET0 (mm)")
            st.subheader("7-day forecast (naive persistence)")
            st.plotly_chart(fig_f, use_container_width=True)
            st.caption("Forecast uses recent-week persistence; replace with API.")
    except Exception:
        pass
    # CSV export button (no pandas dependency)
    try:
        buf = StringIO()
        buf.write("day,tmin_c,tmax_c,rain_mm,et0_mm\n")
        n = len(x)
        for i in range(n):
            buf.write(f"{x[i]},{tmin[i]},{tmax[i]},{rain[i]},{et0[i]}\n")
        st.download_button(
            "Download weather CSV",
            data=buf.getvalue(),
            mime="text/csv",
            file_name="weather_timeseries.csv",
        )
    except Exception:
        pass


def _plot_et(history: Mapping[str, Any], *, upto_idx: int | None = None) -> None:
    fig = go.Figure()
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    evap = (
        history.get("evap_mm", [])
        if upto_idx is None
        else history.get("evap_mm", [])[:upto_idx]
    )
    transp = (
        history.get("transp_mm", [])
        if upto_idx is None
        else history.get("transp_mm", [])[:upto_idx]
    )
    et0 = (
        history.get("et0_mm", [])
        if upto_idx is None
        else history.get("et0_mm", [])[:upto_idx]
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=evap,
            mode="lines",
            name="Evap (mm)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=transp,
            mode="lines",
            name="Transp (mm)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=et0,
            mode="lines",
            name="ET0 PM (mm)",
        )
    )
    if any(history.get("et0_pt_mm", [])):
        et0pt = (
            history.get("et0_pt_mm", [])
            if upto_idx is None
            else history.get("et0_pt_mm", [])[:upto_idx]
        )
        fig.add_trace(
            go.Scatter(
                x=x,
                y=et0pt,
                mode="lines",
                name="ET0 PT (mm)",
            )
        )
    fig.update_layout(yaxis_title="mm")
    st.plotly_chart(fig, use_container_width=True)


def _plot_vpd_stomatal(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> None:
    fig = go.Figure()
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    vpd = (
        history.get("vpd_kpa", [])
        if upto_idx is None
        else history.get("vpd_kpa", [])[:upto_idx]
    )
    stom = (
        history.get("stomatal", [])
        if upto_idx is None
        else history.get("stomatal", [])[:upto_idx]
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=vpd,
            mode="lines",
            name="VPD (kPa)",
            yaxis="y1",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=stom,
            mode="lines",
            name="Stomatal (-)",
            yaxis="y2",
        )
    )
    fig.update_layout(
        yaxis={"title": "VPD (kPa)", "side": "left"},
        yaxis2={
            "title": "Stomatal (-)",
            "overlaying": "y",
            "side": "right",
            "rangemode": "tozero",
        },
    )
    st.plotly_chart(fig, use_container_width=True)


def main(argv: Optional[list[str]] = None) -> None:
    st.set_page_config(page_title="AgroGame Dashboard", layout="wide")
    st.title("AgroGame Dashboard")
    cfg = _collect_sidebar_inputs()
    (
        weather_path,
        days,
        high_contrast,
        irr_day,
        irr_mm,
        fert_day,
        fert_kgha,
        fert_type,
        fert_layer,
        _autorun,
        run,
    ) = cfg

    if run:
        irrigation_schedule: list[tuple[int, float]] = []
        if irr_mm > 0:
            irrigation_schedule.append((int(irr_day), float(irr_mm)))
        fertilizer_schedule: list[tuple[int, float]] = []
        fertilizer_ops: list[tuple[int, float, str, int]] = []
        if fert_kgha > 0:
            fertilizer_ops.append(
                (int(fert_day), float(fert_kgha), str(fert_type), int(fert_layer))
            )

        try:
            history, profile = _run_simulation(
                days=days,
                weather_file=Path(weather_path),
                irrigation_schedule=irrigation_schedule,
                fertilizer_schedule=fertilizer_schedule,
                fertilizer_ops=fertilizer_ops,
            )
        except Exception as e:  # Show load errors in the UI
            st.error("Simulation failed to load inputs or run.")
            st.exception(e)
            return

        # Global day slider controlling all charts
        st.session_state["global_idx"] = _set_global_day_slider(history)

        try:
            _render_all_tabs(
                history,
                profile,
                high_contrast,
                irrigation_schedule,
                fertilizer_schedule,
            )
        except Exception as e:  # Show rendering errors in the UI
            st.error("Rendering failed.")
            st.exception(e)
    else:
        st.info("Set parameters in the sidebar and click 'Run Simulation'.")


# Ensure Streamlit executes the app when running this file directly
if __name__ == "__main__":  # pragma: no cover
    main()
