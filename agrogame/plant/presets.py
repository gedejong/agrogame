from __future__ import annotations

import functools
from dataclasses import dataclass, field, replace
from pathlib import Path

import yaml

from agrogame.config.validation import validate_data
from agrogame.params.canopy import CanopyParams
from agrogame.params.phenology import CropPhenologyParams, GrowthStageThresholds
from agrogame.plant.roots.params import RootParams


@dataclass(frozen=True)
class CropPreset:
    name: str
    phenology: CropPhenologyParams
    canopy: CanopyParams
    roots: RootParams
    n_fixation_credit_kg_ha: float = 0.0
    # Tissue nutrient concentrations (kg nutrient per kg dry matter).
    # Used to compute daily N/P demand from biomass increment.
    # DSSAT: maize ~0.03 N, ~0.003 P; wheat ~0.025 N, ~0.003 P.
    tissue_n_conc_kg_kg: float = 0.03
    tissue_p_conc_kg_kg: float = 0.003
    key: str = ""


@dataclass
class CropLibrary:
    crops: dict[str, CropPreset]
    climate_overrides: dict[str, dict[str, CropPreset]] = field(default_factory=dict)

    def get_preset(self, crop_key: str, climate_key: str | None = None) -> CropPreset:
        """Get crop preset, applying climate-specific overrides if available."""
        base = self.crops[crop_key]
        if climate_key and crop_key in self.climate_overrides:
            overrides = self.climate_overrides[crop_key]
            if climate_key in overrides:
                return overrides[climate_key]
        return base


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
        frost_threshold_c=float(c.get("frost_threshold_c", 0.0)),
        frost_damage_fraction=float(c.get("frost_damage_fraction", 0.3)),
        heat_damage_threshold_c=float(c.get("heat_damage_threshold_c", 35.0)),
        heat_grain_reduction_fraction=float(
            c.get("heat_grain_reduction_fraction", 0.5)
        ),
        waterlog_days_for_damage=int(c.get("waterlog_days_for_damage", 3)),
        waterlog_lai_loss_fraction=float(c.get("waterlog_lai_loss_fraction", 0.15)),
    )


def _build_roots(raw: dict) -> RootParams:
    r = raw.get("roots", {})
    defaults = RootParams()
    return RootParams(
        max_depth_cm=float(r.get("max_depth_cm", 120.0)),
        growth_rate_cm_per_day=float(r.get("growth_rate_cm_per_day", 1.5)),
        distribution=r.get("distribution", "exponential"),
        root_allocation_fraction=float(
            r.get("root_allocation_fraction", defaults.root_allocation_fraction)
        ),
    )


def _apply_canopy_overrides(base: CanopyParams, overrides: dict) -> CanopyParams:
    """Apply partial canopy overrides on top of a base CanopyParams."""
    fields: dict = {}
    _MAP = {
        "rue_g_per_mj": "radiation_use_efficiency_g_per_mj",
        "sla_m2_per_g": "specific_leaf_area_m2_per_g",
    }
    for yaml_key, val in overrides.items():
        field_name = _MAP.get(yaml_key, yaml_key)
        if hasattr(base, field_name):
            fields[field_name] = type(getattr(base, field_name))(val)
    return replace(base, **fields) if fields else base


def _apply_phenology_overrides(
    base: CropPhenologyParams, overrides: dict
) -> CropPhenologyParams:
    """Apply partial phenology overrides on top of base params."""
    thresh_fields: dict = {}
    phen_fields: dict = {}
    for yaml_key, val in overrides.items():
        if yaml_key in ("emergence_gdd", "flowering_gdd", "maturity_gdd"):
            thresh_fields[yaml_key] = float(val)
        elif hasattr(base, yaml_key):
            phen_fields[yaml_key] = type(getattr(base, yaml_key))(val)
    if thresh_fields:
        new_thresh = replace(
            base.thresholds,
            **{k: thresh_fields[k] for k in thresh_fields},
        )
        phen_fields["thresholds"] = new_thresh
    return replace(base, **phen_fields) if phen_fields else base


@functools.lru_cache(maxsize=4)
def _load_crop_presets_cached(p: Path) -> CropLibrary:
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    validate_data(data, "crop_preset")
    crops: dict[str, CropPreset] = {}
    all_overrides: dict[str, dict[str, CropPreset]] = {}

    for key, raw in data.get("crops", {}).items():
        base = CropPreset(
            name=raw["name"],
            phenology=_build_phenology(raw),
            canopy=_build_canopy(raw),
            roots=_build_roots(raw),
            n_fixation_credit_kg_ha=float(raw.get("n_fixation_credit_kg_ha", 0.0)),
            tissue_n_conc_kg_kg=float(raw.get("tissue_n_conc_kg_kg", 0.03)),
            tissue_p_conc_kg_kg=float(raw.get("tissue_p_conc_kg_kg", 0.003)),
            key=key,
        )
        crops[key] = base

        # Parse per-climate overrides
        climate_ovr = raw.get("climate_overrides", {})
        if climate_ovr:
            all_overrides[key] = {}
            for climate_key, ovr in climate_ovr.items():
                canopy = _apply_canopy_overrides(base.canopy, ovr.get("canopy", {}))
                phenology = _apply_phenology_overrides(
                    base.phenology, ovr.get("phenology", {})
                )
                all_overrides[key][climate_key] = replace(
                    base, canopy=canopy, phenology=phenology
                )

    return CropLibrary(crops=crops, climate_overrides=all_overrides)


def load_crop_presets(path: Path | None = None) -> CropLibrary:
    """Load crop presets from YAML, validated against JSON Schema."""
    p = (path or _DEFAULT_PATH).resolve()
    return _load_crop_presets_cached(p)
