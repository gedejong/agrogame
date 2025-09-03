from __future__ import annotations
from pathlib import Path
from datetime import timedelta
from typing import Optional, Any, Dict, Mapping, cast

import plotly.graph_objects as go
import streamlit as st

from agrogame.events import EventBus
from agrogame.sim.orchestrator import build_default_orchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather
from agrogame.weather.utils import vpd_kpa
from agrogame.weather.types import WeatherRecord
from agrogame.soil.nitrogen.state import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phenology.types import PhenologyStage
from agrogame.atmosphere.et import Evapotranspiration, EtParams
from agrogame.soil.models import SoilProfile
from agrogame.atmosphere.et.ports import (
    WaterProfile as ETWaterProfile,
    WaterState as ETWaterState,
    WaterActuator,
)


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

    bus = EventBus()
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(event_bus=bus, state=nstate)
    orch = build_default_orchestrator()
    et_mod = Evapotranspiration(EtParams())

    weather = load_weather(weather_file)

    # If the provided weather file is shorter than requested days, extend by
    # cycling existing records and incrementing the date. This is intended for
    # demo-only behavior so the dashboard shows a full season with the sample file.
    records: list[WeatherRecord] = list(weather.records)
    if days > len(records) and records:
        last_day = records[-1].day
        base = list(records)
        k = 0
        while len(records) < days:
            tmpl = base[k % len(base)]
            k += 1
            last_day = last_day + timedelta(days=1)
            records.append(
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

    history: Dict[str, Any] = {
        "day": [],
        "lai": [],
        "biomass_g_m2": [],
        "theta_layers": [[] for _ in profile.layers],
        "no3_layers": [[] for _ in profile.layers],
        "nh4_layers": [[] for _ in profile.layers],
        "root_depth_cm": [],
        "stage": [],
        "rain_mm": [],
        "tmin_c": [],
        "tmax_c": [],
        "et0_mm": [],
        "et0_pt_mm": [],
        "evap_mm": [],
        "transp_mm": [],
        "vpd_kpa": [],
        "stomatal": [],
        "water_stress": [],
    }

    irrig_map = dict(irrigation_schedule or [])
    fert_map = dict(fertilizer_schedule or [])
    fert_ops = list(fertilizer_ops or [])

    for i in range(min(days, len(records))):
        rec = records[i]
        # Rainfall: use precipitation from the weather file only
        rain = rec.precip_mm or 0.0
        irrigation = irrig_map.get(i, 0.0)

        # Optional fertilization (supports type and layer)
        if fert_ops:
            for d, amt, ftype, layer_idx in fert_ops:
                if d == i and amt > 0.0:
                    if ftype == "urea":
                        ncycle.apply_urea(layer=layer_idx, amount_kg_ha=amt)
                    else:
                        ncycle.apply_ammonium_nitrate(layer=layer_idx, amount_kg_ha=amt)
        else:
            # Backward compatibility with simple schedule (AN to top layer)
            fert_amt = fert_map.get(i, 0.0)
            if fert_amt > 0.0:
                ncycle.apply_ammonium_nitrate(layer=0, amount_kg_ha=fert_amt)

        water.update_daily(
            profile,
            wstate,
            DailyDrivers(
                rainfall_mm=rain, evaporation_mm=0.0, irrigation_mm=irrigation
            ),
        )
        # Guard soil water theta from drifting: update from state directly
        # (water.update_daily already mutates wstate)

        par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
        rn = rec.net_radiation_mj_m2 or rec.shortwave_mj_m2 or 12.0
        tmean = 0.5 * (rec.tmin_c + rec.tmax_c)
        et0 = et_mod.et0(
            temp_mean_c=tmean,
            net_radiation_mj_m2=rn,
            method="penman-monteith",
            wind_m_s=rec.wind_m_s or 2.0,
            relative_humidity_pct=rec.relative_humidity_pct or 60.0,
        )
        history["et0_mm"].append(et0)
        # Priestley-Taylor reference for context
        try:
            et0_pt = et_mod.priestley_taylor(temp_mean_c=tmean, net_radiation_mj_m2=rn)
        except Exception:
            et0_pt = None
        history["et0_pt_mm"].append(et0_pt)

        # Potential ET components (VPD-aware) and actual ET using soil state
        vpd = vpd_kpa(tmean, rec.relative_humidity_pct or 60.0)
        comps = et_mod.potential_components_with_vpd(
            et0_mm=et0, lai=orch.canopy.state.lai, vpd_kpa=vpd
        )
        # Evaporate canopy first; reduce soil evaporation accordingly
        canopy_evap = 0.0
        try:
            # Optional: if interception state is available; else skip
            from agrogame.soil.canopy.interception import InterceptionState

            _istate = InterceptionState()  # stateless use for diagnostic only
            canopy_evap = _istate.evaporate(comps.potential_evap_mm)
        except Exception:
            canopy_evap = 0.0
        comps_adj = type(comps)(
            potential_evap_mm=max(0.0, comps.potential_evap_mm - canopy_evap),
            potential_transp_mm=comps.potential_transp_mm,
            et0_mm=comps.et0_mm,
        )
        # Root fractions if available, else uniform
        try:
            rf = (
                list(getattr(orch.root_state, "layer_fractions", []))
                if getattr(orch, "root_state", None) is not None
                else []
            )
        except Exception:
            rf = []
        if not rf:
            rf = [1.0 / max(1, len(profile.layers))] * max(1, len(profile.layers))
        actual = et_mod.actual_et(
            cast(ETWaterProfile, profile),
            cast(ETWaterState, wstate),
            cast(WaterActuator, water),
            comps_adj,
            rf,
        )
        history["evap_mm"].append(actual.evaporation_mm + canopy_evap)
        history["transp_mm"].append(actual.transpiration_mm)

        # Simple stress as supply/demand ratio for transpiration; ensure
        # non-zero demand and cap minimum stress to avoid NaNs downstream
        demand = max(1e-6, comps_adj.potential_transp_mm)
        water_stress = max(0.05, min(1.0, actual.transpiration_mm / demand))
        history["water_stress"].append(water_stress)
        # Stomatal proxy from VPD and model params
        vpd_excess = max(0.0, vpd - et_mod.params.vpd_ref_kpa)
        stomatal = max(0.2, 1.0 - et_mod.params.vpd_sensitivity * vpd_excess)
        history["vpd_kpa"].append(vpd)
        history["stomatal"].append(stomatal)

        orch.step_day(
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
            water_stress=water_stress,
            n_stress=1.0,
        )
        # Ensure canopy growth responds to PAR and stress by doing a
        # secondary update with current stress (for dashboard visualization)
        try:
            _ = orch.canopy.daily_step(
                incident_par_mj_m2=par,
                temp_factor=1.0,
                water_stress=water_stress,
                n_stress=1.0,
            )
        except Exception:
            pass

        # Nitrogen cycle (use mean air temp as proxy for soil temp)
        _ = ncycle.daily_step(temperature_c=tmean, plant_demand_kg_ha=1.0)

        history["day"].append(rec.day)
        history["lai"].append(orch.canopy.state.lai)
        history["biomass_g_m2"].append(orch.canopy.state.biomass_g_m2)
        # Root depth and phenology stage
        try:
            history["root_depth_cm"].append(orch.root_state.current_depth_cm)
        except Exception:
            history["root_depth_cm"].append(0.0)
        stage = getattr(getattr(orch.phenology, "state", None), "stage", None)
        history["stage"].append(
            stage.value if isinstance(stage, PhenologyStage) else str(stage)
        )
        for li, _layer in enumerate(profile.layers):
            # store volumetric water content per layer
            if len(history["theta_layers"][li]) == i:
                history["theta_layers"][li].append(wstate.theta[li])
            else:
                history["theta_layers"][li][i] = wstate.theta[li]
            # nitrogen pools
            if len(history["no3_layers"][li]) == i:
                history["no3_layers"][li].append(nstate.no3[li])
                history["nh4_layers"][li].append(nstate.nh4[li])
            else:
                history["no3_layers"][li][i] = nstate.no3[li]
                history["nh4_layers"][li][i] = nstate.nh4[li]
        history["rain_mm"].append(rain)
        history["tmin_c"].append(rec.tmin_c)
        history["tmax_c"].append(rec.tmax_c)

    return history, profile


def _plot_soil_moisture(history: Mapping[str, Any], profile: SoilProfile) -> None:
    fig = go.Figure()
    for i, _layer in enumerate(profile.layers):
        fig.add_trace(
            go.Scatter(
                x=history["day"],
                y=history["theta_layers"][i],
                mode="lines",
                name=f"Layer {i+1} θ (m³/m³)",
            )
        )
    fig.update_layout(yaxis_title="Volumetric water content (m³/m³)")
    st.plotly_chart(fig, use_container_width=True)


def _plot_nitrogen(history: Mapping[str, Any], profile: SoilProfile) -> None:
    tabs = st.tabs(["NO3 (kg/ha)", "NH4 (kg/ha)"])
    with tabs[0]:
        fig_no3 = go.Figure()
        for i, _layer in enumerate(profile.layers):
            fig_no3.add_trace(
                go.Scatter(
                    x=history["day"],
                    y=history["no3_layers"][i],
                    mode="lines",
                    name=f"Layer {i+1} NO3",
                )
            )
        fig_no3.update_layout(yaxis_title="NO3 (kg/ha)")
        st.plotly_chart(fig_no3, use_container_width=True)
    with tabs[1]:
        fig_nh4 = go.Figure()
        for i, _layer in enumerate(profile.layers):
            fig_nh4.add_trace(
                go.Scatter(
                    x=history["day"],
                    y=history["nh4_layers"][i],
                    mode="lines",
                    name=f"Layer {i+1} NH4",
                )
            )
        fig_nh4.update_layout(yaxis_title="NH4 (kg/ha)")
        st.plotly_chart(fig_nh4, use_container_width=True)


def _plot_biomass(history: Mapping[str, Any]) -> None:
    fig = go.Figure(
        data=[go.Scatter(x=history["day"], y=history["biomass_g_m2"], mode="lines")]
    )
    fig.update_layout(yaxis_title="Biomass (g m⁻²)")
    st.plotly_chart(fig, use_container_width=True)
    if history.get("water_stress"):
        st.metric("Water Stress (0-1)", f"{history['water_stress'][-1]:.2f}")


def _plot_root_depth(history: Mapping[str, Any]) -> None:
    fig = go.Figure(
        data=[go.Scatter(x=history["day"], y=history["root_depth_cm"], mode="lines")]
    )
    fig.update_layout(yaxis_title="Root depth (cm)")
    st.plotly_chart(fig, use_container_width=True)


def _plot_phenology(history: Mapping[str, Any]) -> None:
    stages = [str(s) for s in history.get("stage", [])]
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


def _plot_weather(history: Mapping[str, Any]) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=history["day"], y=history["tmin_c"], mode="lines", name="Tmin")
    )
    fig.add_trace(
        go.Scatter(x=history["day"], y=history["tmax_c"], mode="lines", name="Tmax")
    )
    fig.add_trace(
        go.Bar(x=history["day"], y=history["rain_mm"], name="Rain (mm)", opacity=0.4)
    )
    fig.add_trace(
        go.Scatter(x=history["day"], y=history["et0_mm"], mode="lines", name="ET0 PM")
    )
    if any(history.get("et0_pt_mm", [])):
        fig.add_trace(
            go.Scatter(
                x=history["day"],
                y=history["et0_pt_mm"],
                mode="lines",
                name="ET0 PT",
            )
        )
    fig.update_layout(yaxis_title="Temp (°C) / Rain & ET0 (mm)")
    st.plotly_chart(fig, use_container_width=True)


def _plot_et(history: Mapping[str, Any]) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history["day"],
            y=history.get("evap_mm", []),
            mode="lines",
            name="Evap (mm)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=history["day"],
            y=history.get("transp_mm", []),
            mode="lines",
            name="Transp (mm)",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=history["day"],
            y=history.get("et0_mm", []),
            mode="lines",
            name="ET0 PM (mm)",
        )
    )
    if any(history.get("et0_pt_mm", [])):
        fig.add_trace(
            go.Scatter(
                x=history["day"],
                y=history.get("et0_pt_mm", []),
                mode="lines",
                name="ET0 PT (mm)",
            )
        )
    fig.update_layout(yaxis_title="mm")
    st.plotly_chart(fig, use_container_width=True)


def _plot_vpd_stomatal(history: Mapping[str, Any]) -> None:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=history["day"],
            y=history.get("vpd_kpa", []),
            mode="lines",
            name="VPD (kPa)",
            yaxis="y1",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=history["day"],
            y=history.get("stomatal", []),
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

    st.sidebar.header("Scenario")
    weather_path = st.sidebar.text_input(
        "Weather file", value=str(Path("data/weather/sample.csv").resolve())
    )
    days = st.sidebar.number_input("Days", min_value=10, max_value=365, value=120)
    st.sidebar.header("Management (optional)")
    irr_day = st.sidebar.number_input("Irrigation day index", min_value=0, value=0)
    irr_mm = st.sidebar.number_input("Irrigation amount (mm)", min_value=0.0, value=0.0)
    fert_day = st.sidebar.number_input("Fertilizer day index", min_value=0, value=0)
    fert_kgha = st.sidebar.number_input(
        "Fertilizer amount (kg N/ha)", min_value=0.0, value=0.0
    )
    fert_type = st.sidebar.selectbox("Fertilizer type", ["ammonium_nitrate", "urea"])
    fert_layer = st.sidebar.number_input("Fertilizer layer index", min_value=0, value=0)
    # Autorun support via query param or checkbox
    autorun_param = "0"
    try:
        # streamlit >= 1.27
        autorun_param = str(getattr(st, "query_params", {}).get("autorun", "0"))
    except Exception:
        try:
            autorun_param = st.experimental_get_query_params().get("autorun", ["0"])[0]
        except Exception:
            autorun_param = "0"
    autorun_default = autorun_param == "1"
    autorun = st.sidebar.checkbox("Auto-run on load", value=autorun_default or True)
    run = st.sidebar.button("Run Simulation") or autorun

    if run:
        irrigation_schedule = []
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

        try:
            tab1, tab2, tab3, tab4 = st.tabs(["Soil", "Crop", "Management", "Weather"])
            with tab1:
                col1, col2 = st.columns(2)
                with col1:
                    st.subheader("Soil moisture by layer")
                    _plot_soil_moisture(history, profile)
                with col2:
                    st.subheader("Soil nitrogen by layer")
                    _plot_nitrogen(history, profile)

            with tab2:
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("Biomass accumulation")
                    _plot_biomass(history)
                with c2:
                    st.subheader("Root depth")
                    _plot_root_depth(history)
                st.subheader("Phenology timeline")
                _plot_phenology(history)
                if history["stage"]:
                    st.metric("Phenology stage", history["stage"][-1])

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
                    _plot_weather(history)
                with w2:
                    st.subheader("ET components")
                    _plot_et(history)
                st.subheader("VPD and stomatal factor")
                _plot_vpd_stomatal(history)
        except Exception as e:  # Show rendering errors in the UI
            st.error("Rendering failed.")
            st.exception(e)
    else:
        st.info("Set parameters in the sidebar and click 'Run Simulation'.")


# Ensure Streamlit executes the app when running this file directly
if __name__ == "__main__":  # pragma: no cover
    main()
