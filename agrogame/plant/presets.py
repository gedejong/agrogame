from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import yaml

from agrogame.config.validation import validate_data
from agrogame.soil.canopy.params import CanopyParams
from agrogame.soil.phenology.params import CropPhenologyParams, GrowthStageThresholds
from agrogame.plant.roots.params import RootParams


@dataclass(frozen=True)
class CropPreset:
    name: str
    phenology: CropPhenologyParams
    canopy: CanopyParams
    roots: RootParams


@dataclass
class CropLibrary:
    crops: Dict[str, CropPreset]


_DEFAULT_PATH = Path("data/crops/presets.yaml")


def _build_phenology(raw: dict) -> CropPhenologyParams:
    ph = raw["phenology"]
    return CropPhenologyParams(
        base_temperature_c=float(ph["base_temperature_c"]),
        max_temperature_c=float(ph["max_temperature_c"]),
        thresholds=GrowthStageThresholds(
            emergence_gdd=float(ph["emergence_gdd"]),
            flowering_gdd=float(ph["flowering_gdd"]),
            maturity_gdd=float(ph["maturity_gdd"]),
        ),
        photoperiod_sensitivity=ph.get("photoperiod_sensitivity"),
        vernalization_required_units=ph.get("vernalization_required_units"),
    )


def _build_canopy(raw: dict) -> CanopyParams:
    c = raw["canopy"]
    return CanopyParams(
        extinction_coefficient_k=float(c["extinction_coefficient_k"]),
        radiation_use_efficiency_g_per_mj=float(c["rue_g_per_mj"]),
        specific_leaf_area_m2_per_g=float(c["sla_m2_per_g"]),
        lai_max=float(c["lai_max"]),
        senescence_rate_per_day=float(c.get("senescence_rate_per_day", 0.01)),
        temp_base_c=float(c.get("temp_base_c", 8.0)),
        temp_opt_c=float(c.get("temp_opt_c", 30.0)),
        temp_max_c=float(c.get("temp_max_c", 42.0)),
        initial_lai_at_emergence=float(c.get("initial_lai_at_emergence", 0.1)),
        senescence_vegetative_fraction=float(
            c.get("senescence_vegetative_fraction", 0.1)
        ),
        stress_memory_days=int(c.get("stress_memory_days", 7)),
        wilt_stress_threshold=float(c.get("wilt_stress_threshold", 0.3)),
        wilt_days_for_damage=int(c.get("wilt_days_for_damage", 5)),
        wilt_lai_loss_fraction=float(c.get("wilt_lai_loss_fraction", 0.1)),
        leaf_fraction_vegetative=float(c.get("leaf_fraction_vegetative", 0.7)),
        leaf_fraction_flowering=float(c.get("leaf_fraction_flowering", 0.4)),
        leaf_fraction_grain_fill=float(c.get("leaf_fraction_grain_fill", 0.15)),
        senescence_flowering_fraction=float(
            c.get("senescence_flowering_fraction", 0.5)
        ),
        senescence_grain_fill_max=float(c.get("senescence_grain_fill_max", 2.0)),
        grain_fill_duration_gdd=float(c.get("grain_fill_duration_gdd", 900.0)),
        harvest_index=float(c.get("harvest_index", 0.45)),
        remobilization_fraction=float(c.get("remobilization_fraction", 0.0)),
    )


def _build_roots(raw: dict) -> RootParams:
    r = raw.get("roots", {})
    return RootParams(
        max_depth_cm=float(r.get("max_depth_cm", 120.0)),
        growth_rate_cm_per_day=float(r.get("growth_rate_cm_per_day", 1.5)),
        distribution=r.get("distribution", "exponential"),
    )


@functools.lru_cache(maxsize=4)
def _load_crop_presets_cached(p: Path) -> CropLibrary:
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate_data(data, "crop_preset")
    crops: Dict[str, CropPreset] = {}
    for key, raw in data.get("crops", {}).items():
        crops[key] = CropPreset(
            name=raw["name"],
            phenology=_build_phenology(raw),
            canopy=_build_canopy(raw),
            roots=_build_roots(raw),
        )
    return CropLibrary(crops=crops)


def load_crop_presets(path: Path | None = None) -> CropLibrary:
    """Load crop presets from YAML, validated against JSON Schema."""
    p = (path or _DEFAULT_PATH).resolve()
    return _load_crop_presets_cached(p)
