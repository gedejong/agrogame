from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping, NamedTuple, Optional

import streamlit as st

from agrogame.dashboard.charts import (
    build_biomass_fig,
    build_enzyme_groups_fig,
    build_et_fig,
    build_interception_fig,
    build_lai_fig,
    build_micro_activity_fig,
    build_microbes_fig,
    build_nitrogen_fig,
    build_phenology_fig,
    build_root_depth_fig,
    build_soil_moisture_fig,
    build_stress_timeseries_fig,
    build_vpd_stomatal_fig,
    build_weather_fig,
)
from agrogame.dashboard.export import (
    biomass_csv,
    root_depth_csv,
    soil_moisture_csv,
    weather_csv,
)
from agrogame.dashboard.simulation import _run_simulation
from agrogame.soil.models import SoilProfile


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


def _render_soil_tab(
    history: Mapping[str, Any],
    profile: SoilProfile,
    high_contrast: bool,
    upto: int | None,
) -> None:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Soil moisture by layer")
        fig = build_soil_moisture_fig(
            history, profile, upto_idx=upto, high_contrast=high_contrast
        )
        st.plotly_chart(fig, use_container_width=True)
        st.download_button(
            "Download soil moisture CSV",
            data=soil_moisture_csv(history, profile, upto_idx=upto),
            mime="text/csv",
            file_name="soil_moisture_timeseries.csv",
        )
    with col2:
        st.subheader("Soil nitrogen by layer")
        fig_no3, fig_nh4 = build_nitrogen_fig(history, profile, upto_idx=upto)
        n_tabs = st.tabs(["NO3 (kg/ha)", "NH4 (kg/ha)"])
        with n_tabs[0]:
            st.plotly_chart(fig_no3, use_container_width=True)
        with n_tabs[1]:
            st.plotly_chart(fig_nh4, use_container_width=True)
    st.subheader("Microbial biomass (totals)")
    st.plotly_chart(
        build_microbes_fig(history, upto_idx=upto), use_container_width=True
    )
    st.subheader("Enzyme group totals (C cost)")
    st.plotly_chart(
        build_enzyme_groups_fig(history, upto_idx=upto), use_container_width=True
    )
    st.subheader("Microbial activity (average)")
    st.plotly_chart(
        build_micro_activity_fig(history, upto_idx=upto), use_container_width=True
    )


def _render_crop_tab(history: Mapping[str, Any], upto: int | None) -> None:
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Biomass accumulation")
        st.plotly_chart(
            build_biomass_fig(history, upto_idx=upto), use_container_width=True
        )
        st.download_button(
            "Download biomass CSV",
            data=biomass_csv(history, upto_idx=upto),
            mime="text/csv",
            file_name="biomass_timeseries.csv",
        )
        _render_stress_metrics(history, upto)
        _render_yield_projection(history)
    with c2:
        st.subheader("Root depth")
        st.plotly_chart(
            build_root_depth_fig(history, upto_idx=upto), use_container_width=True
        )
        st.download_button(
            "Download root depth CSV",
            data=root_depth_csv(history, upto_idx=upto),
            mime="text/csv",
            file_name="root_depth_timeseries.csv",
        )
        _render_root_animation(history)
    st.subheader("Phenology timeline")
    phenology_fig = build_phenology_fig(history, upto_idx=upto)
    if phenology_fig is None:
        st.info("No phenology data available.")
    else:
        st.plotly_chart(phenology_fig, use_container_width=True)
    _render_phenology_progress(history)
    if history.get("stage"):
        st.metric("Phenology stage", history["stage"][-1])
    st.subheader("Stress factors")
    st.plotly_chart(
        build_stress_timeseries_fig(history, upto_idx=upto),
        use_container_width=True,
    )
    _render_nutrient_badges(history)
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Leaf area index (LAI)")
        st.plotly_chart(build_lai_fig(history, upto_idx=upto), use_container_width=True)
    with col4:
        st.subheader("PAR interception")
        st.plotly_chart(
            build_interception_fig(history, upto_idx=upto), use_container_width=True
        )


def _render_stress_metrics(history: Mapping[str, Any], upto: int | None) -> None:
    if not history.get("water_stress"):
        return
    idx = -1 if upto is None else upto - 1
    c_ws, c_ns, c_ps = st.columns(3)
    with c_ws:
        ws_last = history["water_stress"][idx]
        st.metric("Water stress", f"{float(ws_last):.2f}")
    with c_ns:
        n_series = history.get("n_stress", [])
        n_display: Optional[float] = None
        if n_series:
            val = n_series[idx]
            if val is not None:
                n_display = float(val)
        if n_display is None:
            n_total = history.get("n_total_kgha", [0])[idx]
            n_display = max(0.0, min(1.0, float(n_total or 0.0) / 150.0))
        st.metric("N stress", f"{n_display:.2f}")
    with c_ps:
        p_series = history.get("p_stress", [])
        p_val = p_series[idx] if p_series else None
        if p_val is not None:
            st.metric("P stress", f"{float(p_val):.2f}")


def _render_yield_projection(history: Mapping[str, Any]) -> None:
    biomass = float(history.get("biomass_g_m2", [0.0])[-1] or 0.0)
    harvest_index = 0.5
    yield_tha = (biomass / 100.0) * harvest_index
    lo = yield_tha * 0.8
    hi = yield_tha * 1.2
    st.metric(
        "Yield projection (t/ha)",
        f"{yield_tha:.1f}",
        help=f"80%\u2013120% CI: {lo:.1f}\u2013{hi:.1f} t/ha",
    )


def _render_root_animation(history: Mapping[str, Any]) -> None:
    play = st.button("Play root animation", key="root_anim_play")
    if not play:
        return
    placeholder = st.empty()
    max_i = int(st.session_state.get("global_idx", len(history["day"])))
    for frame in range(1, max_i + 1):
        with placeholder.container():
            st.plotly_chart(
                build_root_depth_fig(history, upto_idx=frame),
                use_container_width=True,
            )
        time.sleep(0.04)


def _stage_fraction(
    stage: str, gdd: float, te: float, tf: float, tm: float
) -> float | None:
    if stage == "planted":
        return max(0.0, min(1.0, gdd / max(1e-6, te)))
    if stage == "vegetative":
        return max(0.0, min(1.0, (gdd - te) / max(1e-6, tf - te)))
    if stage == "grain_fill":
        return max(0.0, min(1.0, (gdd - tf) / max(1e-6, tm - tf)))
    if stage in ("emerged", "flowering", "maturity"):
        return 1.0
    return None


def _render_phenology_progress(history: Mapping[str, Any]) -> None:
    last_stage = (history.get("stage", []) or [None])[-1]
    last_gdd = (history.get("gdd_accum", []) or [None])[-1]
    te = history.get("thr_emergence") or 0.0
    tf = history.get("thr_flowering") or te
    tm = history.get("thr_maturity") or tf
    frac = None
    if last_gdd is not None and isinstance(last_stage, str):
        frac = _stage_fraction(last_stage, last_gdd, te, tf, tm)
    if frac is not None:
        st.progress(frac, text=f"Stage {last_stage}: {int(frac * 100)}%")


def _render_nutrient_badges(history: Mapping[str, Any]) -> None:
    n_total = float(history.get("n_total_kgha", [0.0])[-1] or 0.0)
    if n_total >= 120:
        n_badge = "\U0001f7e2 N sufficient"
    elif n_total >= 60:
        n_badge = "\U0001f7e1 N moderate"
    else:
        n_badge = "\U0001f534 N low"
    st.markdown(n_badge)


def _render_management_tab(
    irrigation_schedule: list[tuple[int, float]],
    fertilizer_schedule: list[tuple[int, float]],
) -> None:
    st.write("Management actions applied in this run:")
    if irrigation_schedule:
        st.write(
            f"Irrigation: day {irrigation_schedule[0][0]}, "
            f"{irrigation_schedule[0][1]} mm"
        )
    else:
        st.write("Irrigation: none")
    if fertilizer_schedule:
        st.write(
            f"Fertilizer (AN): day {fertilizer_schedule[0][0]}, "
            f"{fertilizer_schedule[0][1]} kg/ha"
        )
    else:
        st.write("Fertilizer: none")


def _render_weather_tab(history: Mapping[str, Any], upto: int | None) -> None:
    w1, w2 = st.columns(2)
    with w1:
        st.subheader("Weather overview")
        weather_fig, forecast_fig = build_weather_fig(history, upto_idx=upto)
        st.plotly_chart(weather_fig, use_container_width=True)
        tmin = history["tmin_c"] if upto is None else history["tmin_c"][:upto]
        tmax = history["tmax_c"] if upto is None else history["tmax_c"][:upto]
        rain = history["rain_mm"] if upto is None else history["rain_mm"][:upto]
        et0 = history["et0_mm"] if upto is None else history["et0_mm"][:upto]
        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.metric("Tmin (\u00b0C)", f"{tmin[-1]:.1f}")
        with mc2:
            st.metric("Tmax (\u00b0C)", f"{tmax[-1]:.1f}")
        with mc3:
            st.metric("Rain (mm)", f"{rain[-1]:.1f}")
        with mc4:
            st.metric("ET0 (mm)", f"{et0[-1]:.1f}")
        if forecast_fig is not None:
            st.subheader("7-day forecast (naive persistence)")
            st.plotly_chart(forecast_fig, use_container_width=True)
            st.caption("Forecast uses recent-week persistence; replace with API.")
        st.download_button(
            "Download weather CSV",
            data=weather_csv(history, upto_idx=upto),
            mime="text/csv",
            file_name="weather_timeseries.csv",
        )
    with w2:
        st.subheader("ET components")
        st.plotly_chart(build_et_fig(history, upto_idx=upto), use_container_width=True)
    st.subheader("VPD and stomatal factor")
    st.plotly_chart(
        build_vpd_stomatal_fig(history, upto_idx=upto), use_container_width=True
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
        _render_soil_tab(history, profile, high_contrast, upto)
    with tab2:
        _render_crop_tab(history, upto)
    with tab3:
        _render_management_tab(irrigation_schedule, fertilizer_schedule)
    with tab4:
        _render_weather_tab(history, upto)


def main(argv: Optional[list[str]] = None) -> None:
    st.set_page_config(page_title="AgroGame Dashboard", layout="wide")
    st.title("AgroGame Dashboard")
    # App readiness marker for e2e tests (present regardless of run state)
    st.markdown(
        '<div id="agrogame-loaded" data-testid="agrogame-loaded">loaded</div>',
        unsafe_allow_html=True,
    )
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
        # Deterministic readiness marker for e2e
        st.markdown(
            '<div id="agrogame-ready" data-testid="agrogame-ready">ready</div>',
            unsafe_allow_html=True,
        )
    else:
        st.info("Set parameters in the sidebar and click 'Run Simulation'.")


# Ensure Streamlit executes the app when running this file directly
if __name__ == "__main__":  # pragma: no cover
    main()
