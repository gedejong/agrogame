from __future__ import annotations
from pathlib import Path
from typing import Optional

import plotly.graph_objects as go
import streamlit as st

from agrogame.events import EventBus
from agrogame.sim.orchestrator import build_default_orchestrator
from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState
from agrogame.soil.water.types import DailyDrivers
from agrogame.weather import load_weather
from agrogame.soil.nitrogen.state import SoilNitrogenState
from agrogame.soil.nitrogen.cycle import NitrogenCycle
from agrogame.soil.phenology.types import PhenologyStage
from agrogame.atmosphere.et import Evapotranspiration, EtParams


def _run_simulation(
    days: int,
    weather_file: Path,
    irrigation_schedule: list[tuple[int, float]] | None = None,
    fertilizer_schedule: list[tuple[int, float]] | None = None,
):
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]

    bus = EventBus()
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    nstate = SoilNitrogenState(profile)
    ncycle = NitrogenCycle(
        event_bus=bus, state=nstate, water_state=wstate, profile=profile
    )
    orch = build_default_orchestrator()
    et_mod = Evapotranspiration(EtParams())

    weather = load_weather(weather_file)

    history: dict[str, list] = {
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
    }

    irrig_map = dict(irrigation_schedule or [])
    fert_map = dict(fertilizer_schedule or [])

    for i in range(min(days, len(weather.records))):
        rec = weather.records[i]
        rain = rec.precip_mm or 0.0
        irrigation = irrig_map.get(i, 0.0)

        # Optional fertilization (top layer simple split)
        fert_amt = fert_map.get(i, 0.0)
        if fert_amt > 0.0:
            ncycle.apply_ammonium_nitrate(layer=0, amount_kg_ha=fert_amt)

        _ = water.update_daily(
            profile,
            wstate,
            DailyDrivers(
                rainfall_mm=rain, evaporation_mm=0.0, irrigation_mm=irrigation
            ),
        )

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

        orch.step_day(
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
            water_stress=1.0,
            n_stress=1.0,
        )

        # Nitrogen cycle (use mean air temp as proxy for soil temp)
        _ = ncycle.daily_step(temperature_c=tmean)

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


def _plot_soil_moisture(history: dict, profile) -> None:
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


def _plot_nitrogen(history: dict, profile) -> None:
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


def _plot_biomass(history: dict) -> None:
    fig = go.Figure(
        data=[go.Scatter(x=history["day"], y=history["biomass_g_m2"], mode="lines")]
    )
    fig.update_layout(yaxis_title="Biomass (g m⁻²)")
    st.plotly_chart(fig, use_container_width=True)


def _plot_root_depth(history: dict) -> None:
    fig = go.Figure(
        data=[go.Scatter(x=history["day"], y=history["root_depth_cm"], mode="lines")]
    )
    fig.update_layout(yaxis_title="Root depth (cm)")
    st.plotly_chart(fig, use_container_width=True)


def _plot_weather(history: dict) -> None:
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
        go.Scatter(x=history["day"], y=history["et0_mm"], mode="lines", name="ET0")
    )
    fig.update_layout(yaxis_title="Temp (°C) / Rain & ET0 (mm)")
    st.plotly_chart(fig, use_container_width=True)


def main(argv: Optional[list[str]] = None) -> None:
    st.set_page_config(page_title="AgroGame Dashboard", layout="wide")

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
        "Fertilizer (kg N/ha, AN)", min_value=0.0, value=0.0
    )
    run = st.sidebar.button("Run Simulation")

    if run:
        irrigation_schedule = []
        if irr_mm > 0:
            irrigation_schedule.append((int(irr_day), float(irr_mm)))
        fertilizer_schedule = []
        if fert_kgha > 0:
            fertilizer_schedule.append((int(fert_day), float(fert_kgha)))

        history, profile = _run_simulation(
            days=days,
            weather_file=Path(weather_path),
            irrigation_schedule=irrigation_schedule,
            fertilizer_schedule=fertilizer_schedule,
        )

        tab1, tab2, tab3, tab4 = st.tabs(["Soil", "Crop", "Management", "Weather"])
        with tab1:
            st.subheader("Soil moisture by layer")
            _plot_soil_moisture(history, profile)
            st.subheader("Soil nitrogen by layer")
            _plot_nitrogen(history, profile)

        with tab2:
            st.subheader("Biomass accumulation")
            _plot_biomass(history)
            st.subheader("Root depth")
            _plot_root_depth(history)
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
            st.subheader("Weather overview")
            _plot_weather(history)
