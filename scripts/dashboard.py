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


def _run_simulation(days: int, weather_file: Path):
    soil_lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = soil_lib.soils["loam_temperate"]

    bus = EventBus()
    water = CascadingBucketWaterModel(event_bus=bus)
    wstate = SoilWaterState(profile)
    orch = build_default_orchestrator()

    weather = load_weather(weather_file)

    history = {
        "day": [],
        "lai": [],
        "biomass_g_m2": [],
        "theta_layers": [[] for _ in profile.layers],
        "rain_mm": [],
    }

    for i in range(min(days, len(weather.records))):
        rec = weather.records[i]

        rain = rec.precip_mm or 0.0
        _ = water.update_daily(
            profile,
            wstate,
            DailyDrivers(rainfall_mm=rain, evaporation_mm=0.0),
        )

        par = (rec.shortwave_mj_m2 or rec.net_radiation_mj_m2 or 12.0) * 0.48
        orch.step_day(
            tmin_c=rec.tmin_c,
            tmax_c=rec.tmax_c,
            par_mj_m2=par,
            water_stress=1.0,
            n_stress=1.0,
        )

        history["day"].append(rec.day)
        history["lai"].append(orch.canopy.state.lai)
        history["biomass_g_m2"].append(orch.canopy.state.biomass_g_m2)
        for li, _layer in enumerate(profile.layers):
            # store volumetric water content per layer
            if len(history["theta_layers"][li]) == i:
                history["theta_layers"][li].append(wstate.theta[li])
            else:
                history["theta_layers"][li][i] = wstate.theta[li]
        history["rain_mm"].append(rain)

    return history, profile


def _plot_soil_moisture(history, profile):
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


def _plot_biomass(history):
    fig = go.Figure(
        data=[go.Scatter(x=history["day"], y=history["biomass_g_m2"], mode="lines")]
    )
    fig.update_layout(yaxis_title="Biomass (g m⁻²)")
    st.plotly_chart(fig, use_container_width=True)


def main(argv: Optional[list[str]] = None) -> None:
    st.set_page_config(page_title="AgroGame Dashboard", layout="wide")

    st.sidebar.header("Scenario")
    weather_path = st.sidebar.text_input(
        "Weather file", value=str(Path("data/weather/sample.csv").resolve())
    )
    days = st.sidebar.number_input("Days", min_value=10, max_value=365, value=120)
    run = st.sidebar.button("Run Simulation")

    if run:
        history, profile = _run_simulation(days=days, weather_file=Path(weather_path))

        tab1, tab2 = st.tabs(["Soil", "Crop"])
        with tab1:
            st.subheader("Soil moisture by layer")
            _plot_soil_moisture(history, profile)

        with tab2:
            st.subheader("Biomass accumulation")
            _plot_biomass(history)


if __name__ == "__main__":
    main()
