from __future__ import annotations

from io import StringIO
from typing import Any
from collections.abc import Mapping

from agrogame.api.dashboard_facade import SoilProfile


def soil_moisture_csv(
    history: Mapping[str, Any],
    profile: SoilProfile,
    *,
    upto_idx: int | None = None,
) -> str:
    """Return CSV string for soil moisture time series."""
    buf = StringIO()
    header = ["day"] + [f"theta_layer_{i+1}" for i in range(len(profile.layers))]
    buf.write(",".join(header) + "\n")
    n = len(history["day"]) if upto_idx is None else upto_idx
    for idx in range(n):
        row = [str(history["day"][idx])]
        for li in range(len(profile.layers)):
            row.append(f"{history['theta_layers'][li][idx]:.4f}")
        buf.write(",".join(row) + "\n")
    return buf.getvalue()


def biomass_csv(history: Mapping[str, Any], *, upto_idx: int | None = None) -> str:
    """Return CSV string for biomass time series."""
    buf = StringIO()
    n = len(history["day"]) if upto_idx is None else upto_idx
    buf.write("day,biomass_g_m2\n")
    for i in range(n):
        buf.write(f"{history['day'][i]},{history['biomass_g_m2'][i]:.2f}\n")
    return buf.getvalue()


def root_depth_csv(history: Mapping[str, Any], *, upto_idx: int | None = None) -> str:
    """Return CSV string for root depth time series."""
    buf = StringIO()
    n = len(history["day"]) if upto_idx is None else upto_idx
    buf.write("day,root_depth_cm\n")
    for i in range(n):
        buf.write(f"{history['day'][i]},{history['root_depth_cm'][i]:.2f}\n")
    return buf.getvalue()


def weather_csv(history: Mapping[str, Any], *, upto_idx: int | None = None) -> str:
    """Return CSV string for weather time series."""
    buf = StringIO()
    x = history["day"] if upto_idx is None else history["day"][:upto_idx]
    tmin = history["tmin_c"] if upto_idx is None else history["tmin_c"][:upto_idx]
    tmax = history["tmax_c"] if upto_idx is None else history["tmax_c"][:upto_idx]
    rain = history["rain_mm"] if upto_idx is None else history["rain_mm"][:upto_idx]
    et0 = history["et0_mm"] if upto_idx is None else history["et0_mm"][:upto_idx]
    buf.write("day,tmin_c,tmax_c,rain_mm,et0_mm\n")
    n = len(x)
    for i in range(n):
        buf.write(f"{x[i]},{tmin[i]},{tmax[i]},{rain[i]},{et0[i]}\n")
    return buf.getvalue()
