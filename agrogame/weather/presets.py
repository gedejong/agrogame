from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml

from agrogame.config.validation import validate_data


@dataclass(frozen=True)
class ClimatePreset:
    name: str
    latitude_deg: float
    longitude_deg: float
    annual_mean_tmin_c: float
    annual_mean_tmax_c: float
    annual_temp_amplitude_c: float
    annual_mean_precip_mm_day: float
    annual_mean_rh_pct: float
    annual_mean_wind_m_s: float
    annual_mean_shortwave_mj_m2: float
    heatwave_probability: float = 0.0
    frost_probability: float = 0.0
    heavy_rain_probability: float = 0.0
    heatwave_intensity_c: float = 8.0
    frost_intensity_c: float = -5.0
    heavy_rain_intensity_mm: float = 40.0


@dataclass
class ClimateLibrary:
    climates: Dict[str, ClimatePreset]


_DEFAULT_PATH = Path("data/climate/presets.yaml")


@functools.lru_cache(maxsize=4)
def _load_climate_presets_cached(p: Path) -> ClimateLibrary:
    """Load and cache climate presets (internal, expects resolved path)."""
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate_data(data, "climate")
    climates: Dict[str, ClimatePreset] = {}
    for key, raw in data.get("climates", {}).items():
        climates[key] = ClimatePreset(
            name=raw["name"],
            latitude_deg=float(raw["latitude_deg"]),
            longitude_deg=float(raw["longitude_deg"]),
            annual_mean_tmin_c=float(raw["annual_mean_tmin_c"]),
            annual_mean_tmax_c=float(raw["annual_mean_tmax_c"]),
            annual_temp_amplitude_c=float(raw["annual_temp_amplitude_c"]),
            annual_mean_precip_mm_day=float(raw["annual_mean_precip_mm_day"]),
            annual_mean_rh_pct=float(raw["annual_mean_rh_pct"]),
            annual_mean_wind_m_s=float(raw["annual_mean_wind_m_s"]),
            annual_mean_shortwave_mj_m2=float(raw["annual_mean_shortwave_mj_m2"]),
            heatwave_probability=float(raw.get("heatwave_probability", 0.0)),
            frost_probability=float(raw.get("frost_probability", 0.0)),
            heavy_rain_probability=float(raw.get("heavy_rain_probability", 0.0)),
            heatwave_intensity_c=float(raw.get("heatwave_intensity_c", 8.0)),
            frost_intensity_c=float(raw.get("frost_intensity_c", -5.0)),
            heavy_rain_intensity_mm=float(raw.get("heavy_rain_intensity_mm", 40.0)),
        )
    return ClimateLibrary(climates=climates)


def load_climate_presets(path: Path | None = None) -> ClimateLibrary:
    """Load climate presets from YAML, validated against JSON Schema."""
    p = (path or _DEFAULT_PATH).resolve()
    return _load_climate_presets_cached(p)
