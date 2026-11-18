from __future__ import annotations

import functools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    # Monthly rainfall weights (12 values, normalized so mean=1.0).
    # E.g., [0.5, 0.5, 1.5, 2.0, 1.5, 0.3, ...] for bimodal pattern.
    # Empty list means uniform distribution.
    rainfall_monthly_weights: list[float] = field(default_factory=list)
    heatwave_probability: float = 0.0
    frost_probability: float = 0.0
    heavy_rain_probability: float = 0.0
    heatwave_intensity_c: float = 8.0
    frost_intensity_c: float = -5.0
    heavy_rain_intensity_mm: float = 40.0
    # Optional station monthly normals, 12 values Jan→Dec (#500 AC1, ADR-019).
    # When present, the generator takes the day's base value from the entry for
    # its calendar month instead of the legacy annual sinusoid. Empty means the
    # legacy formula. Tmin and Tmax come as a pair; shortwave stands alone.
    monthly_mean_tmin_c: list[float] = field(default_factory=list)
    monthly_mean_tmax_c: list[float] = field(default_factory=list)
    monthly_mean_shortwave_mj_m2: list[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        _check_monthly_normals(self)


# Largest allowed gap between a monthly array's 12-month mean and its
# ``annual_mean_*`` field (#500 AC1 check iii). The YAML rounds both to 2 dp,
# so 0.05 leaves room for rounding and nothing more.
_ANNUAL_MEAN_TOLERANCE = 0.05


def _check_monthly_normals(p: ClimatePreset) -> None:
    """Raise ``ValueError`` if the optional monthly normals are inconsistent.

    The #500 AC1 loader checks, in order: (i) tmin and tmax come as a pair,
    (ii) tmin < tmax in every month, (iii) each array's 12-month mean matches
    its ``annual_mean_*`` field.
    """
    arrays = {
        "monthly_mean_tmin_c": (p.monthly_mean_tmin_c, p.annual_mean_tmin_c),
        "monthly_mean_tmax_c": (p.monthly_mean_tmax_c, p.annual_mean_tmax_c),
        "monthly_mean_shortwave_mj_m2": (
            p.monthly_mean_shortwave_mj_m2,
            p.annual_mean_shortwave_mj_m2,
        ),
    }
    for name, (values, _annual) in arrays.items():
        if values and len(values) != 12:
            raise ValueError(f"{p.name}: {name} needs 12 values, got {len(values)}")
    if bool(p.monthly_mean_tmin_c) != bool(p.monthly_mean_tmax_c):
        raise ValueError(
            f"{p.name}: monthly_mean_tmin_c and monthly_mean_tmax_c must be "
            "given together"
        )
    for month, (lo, hi) in enumerate(
        zip(p.monthly_mean_tmin_c, p.monthly_mean_tmax_c, strict=True), start=1
    ):
        if lo >= hi:
            raise ValueError(
                f"{p.name}: month {month} has tmin {lo} >= tmax {hi} in the "
                "monthly normals"
            )
    for name, (values, annual) in arrays.items():
        _check_annual_mean(p.name, name, values, annual)


def _check_annual_mean(
    preset_name: str, name: str, values: list[float], annual: float
) -> None:
    """Raise ``ValueError`` if a present array's mean misses its annual field."""
    if not values:
        return
    mean = sum(values) / 12.0
    if abs(mean - annual) > _ANNUAL_MEAN_TOLERANCE:
        raise ValueError(
            f"{preset_name}: {name} averages {mean:.3f}, but its annual mean "
            f"field is {annual}; they must agree within {_ANNUAL_MEAN_TOLERANCE}"
        )


@dataclass
class ClimateLibrary:
    climates: dict[str, ClimatePreset]


_DEFAULT_PATH = Path("data/climate/presets.yaml")


def _floats(raw: dict[str, Any], key: str) -> list[float]:
    """An optional numeric array from a raw preset mapping (empty if absent)."""
    return [float(v) for v in raw.get(key, [])]


@functools.lru_cache(maxsize=4)
def _load_climate_presets_cached(p: Path) -> ClimateLibrary:
    """Load and cache climate presets (internal, expects resolved path)."""
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate_data(data, "climate")
    climates: dict[str, ClimatePreset] = {}
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
            rainfall_monthly_weights=[
                float(w) for w in raw.get("rainfall_monthly_weights", [])
            ],
            heatwave_probability=float(raw.get("heatwave_probability", 0.0)),
            frost_probability=float(raw.get("frost_probability", 0.0)),
            heavy_rain_probability=float(raw.get("heavy_rain_probability", 0.0)),
            heatwave_intensity_c=float(raw.get("heatwave_intensity_c", 8.0)),
            frost_intensity_c=float(raw.get("frost_intensity_c", -5.0)),
            heavy_rain_intensity_mm=float(raw.get("heavy_rain_intensity_mm", 40.0)),
            monthly_mean_tmin_c=_floats(raw, "monthly_mean_tmin_c"),
            monthly_mean_tmax_c=_floats(raw, "monthly_mean_tmax_c"),
            monthly_mean_shortwave_mj_m2=_floats(raw, "monthly_mean_shortwave_mj_m2"),
        )
    return ClimateLibrary(climates=climates)


def load_climate_presets(path: Path | None = None) -> ClimateLibrary:
    """Load climate presets from YAML, validated against JSON Schema."""
    p = (path or _DEFAULT_PATH).resolve()
    return _load_climate_presets_cached(p)
