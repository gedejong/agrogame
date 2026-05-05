from __future__ import annotations

from datetime import timedelta
from typing import Any
from collections.abc import Mapping

import plotly.graph_objects as go

from agrogame.soil.models import SoilProfile


def _gradient_hex(color_a: str, color_b: str, steps: int) -> list[str]:
    def to_rgb(h: str) -> tuple[int, int, int]:
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def to_hex(rgb: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*rgb)

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


def build_soil_moisture_fig(
    history: Mapping[str, Any],
    profile: SoilProfile,
    *,
    upto_idx: int | None = None,
    high_contrast: bool = False,
) -> go.Figure:
    fig = go.Figure()
    # Blue -> brown gradient per layer (high-contrast uses darker tones)
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
                name=f"Layer {i+1} \u03b8 (m\u00b3/m\u00b3)",
                hovertemplate=(
                    f"Layer {i+1} \u03b8: %{{y:.3f}} m\u00b3/m\u00b3" "<extra></extra>"
                ),
                line={
                    "color": colors[i % len(colors)],
                    "width": 2 if high_contrast else 1.5,
                },
            )
        )
    fig.update_layout(
        yaxis_title="Volumetric water content (m\u00b3/m\u00b3)",
        template=("plotly_white" if high_contrast else None),
    )
    return fig


def build_nitrogen_fig(
    history: Mapping[str, Any], profile: SoilProfile, *, upto_idx: int | None = None
) -> tuple[go.Figure, go.Figure]:
    """Return (fig_no3, fig_nh4) figures for nitrogen by layer."""
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
    return fig_no3, fig_nh4


def build_biomass_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
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
                hovertemplate="Biomass: %{y:.0f} g m\u207b\u00b2<extra></extra>",
            )
        ]
    )
    fig.update_layout(yaxis_title="Biomass (g m\u207b\u00b2)")
    return fig


def build_root_depth_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
    x = history["day"]
    y = history["root_depth_cm"]
    if upto_idx is not None:
        x = x[:upto_idx]
        y = y[:upto_idx]
    fig = go.Figure(data=[go.Scatter(x=x, y=y, mode="lines")])
    fig.update_layout(yaxis_title="Root depth (cm)")
    return fig


def build_lai_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    lai = (
        history.get("lai", [])
        if upto_idx is None
        else history.get("lai", [])[:upto_idx]
    )
    fig = go.Figure(data=[go.Scatter(x=x, y=lai, mode="lines", name="LAI")])
    fig.update_layout(yaxis_title="LAI (-)")
    return fig


def build_interception_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
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
    fig.add_trace(
        go.Scatter(x=x, y=par, mode="lines", name="PAR (MJ m\u207b\u00b2)", yaxis="y1")
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=par_int,
            mode="lines",
            name="Intercepted PAR (MJ m\u207b\u00b2)",
            yaxis="y1",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x, y=frac, mode="lines", name="Fraction intercepted (-)", yaxis="y2"
        )
    )
    fig.update_layout(
        yaxis={"title": "PAR (MJ m\u207b\u00b2)", "side": "left"},
        yaxis2={
            "title": "Fraction (-)",
            "overlaying": "y",
            "side": "right",
            "rangemode": "tozero",
        },
    )
    return fig


def build_phenology_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure | None:
    """Return phenology bar figure, or None if no data available."""
    stages_full = [str(s) for s in history.get("stage", [])]
    stages = stages_full if upto_idx is None else stages_full[:upto_idx]
    if not stages:
        return None

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
                hovertemplate="%{text} \u00b7 %{x} days<extra></extra>",
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
    return fig


def build_microbes_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
    x = (
        history.get("day", [])
        if upto_idx is None
        else history.get("day", [])[:upto_idx]
    )
    mc = (
        history.get("micro_c_total", [])
        if upto_idx is None
        else history.get("micro_c_total", [])[:upto_idx]
    )
    mn = (
        history.get("micro_n_total", [])
        if upto_idx is None
        else history.get("micro_n_total", [])[:upto_idx]
    )
    fb = (
        history.get("micro_fb_avg", [])
        if upto_idx is None
        else history.get("micro_fb_avg", [])[:upto_idx]
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=x, y=mc, mode="lines", name="Microbial C (kg/ha)", yaxis="y1")
    )
    fig.add_trace(
        go.Scatter(x=x, y=mn, mode="lines", name="Microbial N (kg/ha)", yaxis="y1")
    )
    fig.add_trace(
        go.Scatter(x=x, y=fb, mode="lines", name="Fungal fraction (-)", yaxis="y2")
    )
    fig.update_layout(
        yaxis={"title": "C/N (kg/ha)", "side": "left"},
        yaxis2={
            "title": "Fungal fraction (-)",
            "overlaying": "y",
            "side": "right",
            "rangemode": "tozero",
        },
    )
    return fig


def build_enzyme_groups_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
    x = (
        history.get("day", [])
        if upto_idx is None
        else history.get("day", [])[:upto_idx]
    )
    groups = [
        ("Cellulase", history.get("enzyme_cellulase_c", [])),
        ("Protease", history.get("enzyme_protease_c", [])),
        ("Phosphatase", history.get("enzyme_phosphatase_c", [])),
        ("Urease", history.get("enzyme_urease_c", [])),
    ]
    fig = go.Figure()
    for name, data in groups:
        series = data if upto_idx is None else data[:upto_idx]
        fig.add_trace(go.Bar(x=x, y=series, name=name))
    fig.update_layout(barmode="stack", yaxis_title="C cost (kg/ha\u00b7d)")
    return fig


def build_micro_activity_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
    x = (
        history.get("day", [])
        if upto_idx is None
        else history.get("day", [])[:upto_idx]
    )
    act = (
        history.get("micro_activity_avg", [])
        if upto_idx is None
        else history.get("micro_activity_avg", [])[:upto_idx]
    )
    fig = go.Figure(data=[go.Scatter(x=x, y=act, mode="lines", name="Activity (-)")])
    fig.update_layout(yaxis_title="Microbial activity (-)")
    return fig


def build_weather_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> tuple[go.Figure, go.Figure | None]:
    """Return (main_weather_fig, forecast_fig_or_None)."""
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
    fig.update_layout(yaxis_title="Temp (\u00b0C) / Rain & ET0 (mm)")

    # Naive 7-day forecast (persistence from recent week)
    fig_f: go.Figure | None = None
    if history.get("day"):
        last_day = history["day"][-1]

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
        days_f = [last_day + timedelta(days=i + 1) for i in range(7)]
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
        fig_f.update_layout(yaxis_title="Forecast: Temp (\u00b0C) / Rain & ET0 (mm)")

    return fig, fig_f


def build_et_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
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
    return fig


def build_vpd_stomatal_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
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
    return fig


def build_stress_timeseries_fig(
    history: Mapping[str, Any], *, upto_idx: int | None = None
) -> go.Figure:
    x = history.get("day", [])
    if upto_idx is not None:
        x = x[:upto_idx]
    water = (
        history.get("water_stress", [])
        if upto_idx is None
        else history.get("water_stress", [])[:upto_idx]
    )
    n_s = (
        history.get("n_stress", [])
        if upto_idx is None
        else history.get("n_stress", [])[:upto_idx]
    )
    p_s = (
        history.get("p_stress", [])
        if upto_idx is None
        else history.get("p_stress", [])[:upto_idx]
    )
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=x, y=water, mode="lines", name="Water stress", yaxis="y1")
    )

    # Replace None with gaps for nutrient stress
    def _sanitize(seq: list[Any]) -> list[Any]:
        return [None if (v is None) else float(v) for v in seq]

    if any(n_s):
        fig.add_trace(
            go.Scatter(x=x, y=_sanitize(n_s), mode="lines", name="N stress", yaxis="y1")
        )
    if any(p_s):
        fig.add_trace(
            go.Scatter(x=x, y=_sanitize(p_s), mode="lines", name="P stress", yaxis="y1")
        )
    fig.update_layout(
        yaxis={"title": "Stress (-)", "side": "left", "rangemode": "tozero"}
    )
    return fig
