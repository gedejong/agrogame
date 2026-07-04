"""Interactive scaffolding wizard for crop and soil configuration files.

Drives prompts from a small field-spec table so the crop and soil paths share
one prompt loop. Defaults are seeded from bundled templates (maize, loam);
each prompt shows an inline unit + range hint. Input and output streams are
injectable so the wizard is unit-testable without a TTY.

Design decision (issue #66): the crop path emits the *runtime* crop shape
(``phenology`` / ``canopy`` / ``roots``) so the output loads via
``load_crop_presets``. It is therefore validated structurally against the
``crop_preset`` schema (the same schema the runtime loader uses), NOT the stale
``crop.json`` schema.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO
from collections.abc import Callable

import yaml

from agrogame.config.validation import validate_data
from agrogame.soil.models import SoilLibrary


@dataclass(frozen=True)
class FieldSpec:
    """A single numeric prompt: dotted path into the document, unit and range."""

    path: tuple[str, ...]
    label: str
    unit: str
    minimum: float
    maximum: float
    default: float
    is_int: bool = False

    def hint(self) -> str:
        """Inline hint string, e.g. ``base_temp_c [0-15 degC, default 8.0]``."""
        unit = f" {self.unit}" if self.unit else ""
        default = int(self.default) if self.is_int else self.default
        rng = f"{_fmt(self.minimum)}-{_fmt(self.maximum)}{unit}"
        return f"{self.label} [{rng}, default {default}]: "


def _fmt(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


# --- Templates -------------------------------------------------------------
# Maize seeds the runtime crop shape (phenology/canopy/roots); values track
# data/crops/presets.yaml (DSSAT CERES / NL posteriors).
_MAIZE_TEMPLATE: dict[str, Any] = {
    "name": "Maize (Zea mays)",
    "tissue_n_conc_kg_kg": 0.030,
    "tissue_p_conc_kg_kg": 0.003,
    "phenology": {
        "base_temperature_c": 8.0,
        "max_temperature_c": 35.0,
        "emergence_gdd": 100.0,
        "flowering_gdd": 759.0,
        "maturity_gdd": 1830.0,
    },
    "canopy": {
        "extinction_coefficient_k": 0.54,
        "rue_g_per_mj": 3.56,
        "sla_m2_per_g": 0.02,
        "lai_max": 6.0,
        "harvest_index": 0.50,
    },
    "roots": {
        "max_depth_cm": 150.0,
        "growth_rate_cm_per_day": 2.0,
        "distribution": "exponential",
    },
}

# Loam seeds the soil shape (data/soils/presets.yaml). Three layers, 100 cm.
_LOAM_TEMPLATE: dict[str, Any] = {
    "name": "Loam - Temperate",
    "layers": [
        {
            "depth_cm": 25,
            "texture": "loam",
            "field_capacity": 0.25,
            "wilting_point": 0.12,
            "saturation": 0.45,
            "bulk_density_g_cm3": 1.45,
            "ksat_mm_per_hour": 15.0,
            "organic_matter_pct": 2.0,
            "initial_no3_kg_ha": 10.0,
            "initial_nh4_kg_ha": 4.0,
            "initial_p_kg_ha": 20.0,
        },
        {
            "depth_cm": 35,
            "texture": "loam",
            "field_capacity": 0.24,
            "wilting_point": 0.12,
            "saturation": 0.44,
            "bulk_density_g_cm3": 1.50,
            "ksat_mm_per_hour": 12.0,
            "organic_matter_pct": 1.5,
            "initial_no3_kg_ha": 6.0,
            "initial_nh4_kg_ha": 2.5,
            "initial_p_kg_ha": 12.0,
        },
        {
            "depth_cm": 40,
            "texture": "loam",
            "field_capacity": 0.22,
            "wilting_point": 0.11,
            "saturation": 0.42,
            "bulk_density_g_cm3": 1.55,
            "ksat_mm_per_hour": 10.0,
            "organic_matter_pct": 1.0,
            "initial_no3_kg_ha": 5.0,
            "initial_nh4_kg_ha": 2.0,
            "initial_p_kg_ha": 10.0,
        },
    ],
}

# Crop fields prompted (subset that matters); the rest come from the template.
_CROP_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(("phenology", "base_temperature_c"), "base_temp_c", "degC", 0, 15, 8.0),
    FieldSpec(("phenology", "max_temperature_c"), "max_temp_c", "degC", 20, 45, 35.0),
    FieldSpec(
        ("phenology", "emergence_gdd"), "emergence_gdd", "degC-day", 0, 500, 100.0
    ),
    FieldSpec(
        ("phenology", "flowering_gdd"), "flowering_gdd", "degC-day", 100, 2500, 759.0
    ),
    FieldSpec(
        ("phenology", "maturity_gdd"), "maturity_gdd", "degC-day", 200, 4000, 1830.0
    ),
    FieldSpec(("canopy", "extinction_coefficient_k"), "extinction_k", "", 0, 1, 0.54),
    FieldSpec(("canopy", "rue_g_per_mj"), "rue_g_per_mj", "g/MJ", 0, 6, 3.56),
    FieldSpec(("canopy", "sla_m2_per_g"), "sla_m2_per_g", "m2/g", 0, 0.1, 0.02),
    FieldSpec(("canopy", "lai_max"), "lai_max", "m2/m2", 0, 12, 6.0),
    FieldSpec(("canopy", "harvest_index"), "harvest_index", "", 0, 1, 0.50),
    FieldSpec(("roots", "max_depth_cm"), "root_max_depth_cm", "cm", 0, 400, 150.0),
    FieldSpec(
        ("roots", "growth_rate_cm_per_day"), "root_growth_cm_day", "cm/day", 0, 10, 2.0
    ),
)

# Soil fields prompted; applied uniformly to every template layer.
_SOIL_FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(("field_capacity",), "field_capacity", "m3/m3", 0, 0.8, 0.25),
    FieldSpec(("wilting_point",), "wilting_point", "m3/m3", 0, 0.8, 0.12),
    FieldSpec(("saturation",), "saturation", "m3/m3", 0, 0.8, 0.45),
    FieldSpec(("bulk_density_g_cm3",), "bulk_density_g_cm3", "g/cm3", 0.5, 2.0, 1.45),
    FieldSpec(("ksat_mm_per_hour",), "ksat_mm_per_hour", "mm/h", 0, 500, 15.0),
    FieldSpec(("organic_matter_pct",), "organic_matter_pct", "%", 0, 100, 2.0),
    FieldSpec(("initial_no3_kg_ha",), "initial_no3_kg_ha", "kg/ha", 0, 500, 10.0),
    FieldSpec(("initial_nh4_kg_ha",), "initial_nh4_kg_ha", "kg/ha", 0, 500, 4.0),
    FieldSpec(("initial_p_kg_ha",), "initial_p_kg_ha", "kg/ha", 0, 500, 20.0),
)


def _read_line(in_stream: TextIO, out_stream: TextIO, prompt: str) -> str:
    out_stream.write(prompt)
    out_stream.flush()
    line = in_stream.readline()
    return line.strip()


def _prompt_field(spec: FieldSpec, in_stream: TextIO, out_stream: TextIO) -> float:
    """Prompt for one numeric field; re-prompt on unparseable/out-of-range input."""
    while True:
        raw = _read_line(in_stream, out_stream, spec.hint())
        if not raw:
            return int(spec.default) if spec.is_int else spec.default
        try:
            value: float = int(raw) if spec.is_int else float(raw)
        except ValueError:
            out_stream.write(f"  ! '{raw}' is not a number; try again.\n")
            continue
        if value < spec.minimum or value > spec.maximum:
            out_stream.write(
                f"  ! {_fmt(value)} out of range "
                f"[{_fmt(spec.minimum)}-{_fmt(spec.maximum)}]; try again.\n"
            )
            continue
        return value


def _prompt_text(
    in_stream: TextIO, out_stream: TextIO, label: str, default: str
) -> str:
    raw = _read_line(in_stream, out_stream, f"{label} [default {default}]: ")
    return raw or default


def _prompt_choice(
    in_stream: TextIO, out_stream: TextIO, label: str, choices: tuple[str, ...]
) -> str:
    options = "/".join(choices)
    while True:
        raw = _read_line(in_stream, out_stream, f"{label} ({options}) [{choices[0]}]: ")
        choice = raw or choices[0]
        if choice in choices:
            return choice
        out_stream.write(f"  ! choose one of {options}; try again.\n")


def _confirm(in_stream: TextIO, out_stream: TextIO, prompt: str) -> bool:
    raw = _read_line(in_stream, out_stream, f"{prompt} [y/N]: ")
    return raw.lower() in {"y", "yes"}


def _set_path(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    node = target
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def build_crop_document(
    key: str, name: str, values: dict[tuple[str, ...], float]
) -> dict[str, Any]:
    """Assemble the runtime crop document from the maize template + overrides."""
    body = deepcopy(_MAIZE_TEMPLATE)
    body["name"] = name
    for path, value in values.items():
        _set_path(body, path, value)
    return {"crops": {key: body}}


def build_soil_document(
    key: str, name: str, values: dict[tuple[str, ...], float]
) -> dict[str, Any]:
    """Assemble the soil document; prompted values apply to every template layer."""
    body = deepcopy(_LOAM_TEMPLATE)
    body["name"] = name
    for layer in body["layers"]:
        for path, value in values.items():
            layer[path[-1]] = value
    return {"soils": {key: body}}


def _collect(
    fields: tuple[FieldSpec, ...], in_stream: TextIO, out_stream: TextIO
) -> dict[tuple[str, ...], float]:
    return {spec.path: _prompt_field(spec, in_stream, out_stream) for spec in fields}


def _validate_document(kind: str, document: dict[str, Any]) -> None:
    """Full-document validation before writing (raises on failure)."""
    if kind == "soil":
        validate_data(document, "soil")
        SoilLibrary.model_validate(document)
        return
    # Crop: validate against the runtime crop_preset schema (design decision a).
    validate_data(document, "crop_preset")


def _write_document(
    document: dict[str, Any],
    in_stream: TextIO,
    out_stream: TextIO,
    exists: Callable[[Path], bool] = Path.exists,
) -> Path | None:
    """Prompt for an output path and write YAML; confirm before overwriting."""
    raw = _read_line(in_stream, out_stream, "Output path (YAML): ")
    if not raw:
        out_stream.write("No path given; aborted.\n")
        return None
    out_path = Path(raw)
    if exists(out_path) and not _confirm(
        in_stream, out_stream, f"{out_path} exists. Overwrite?"
    ):
        out_stream.write("Left existing file untouched.\n")
        return None
    out_path.write_text(yaml.safe_dump(document, sort_keys=False))
    out_stream.write(f"Wrote {out_path}\n")
    return out_path


def run_wizard(in_stream: TextIO, out_stream: TextIO) -> int:
    """Run the interactive scaffolding wizard over the given streams.

    Returns 0 on success (including a declined overwrite) and 1 if the assembled
    document fails full-document validation.
    """
    kind = _prompt_choice(
        in_stream, out_stream, "Scaffold which config?", ("crop", "soil")
    )
    if kind == "crop":
        key = _prompt_text(in_stream, out_stream, "Crop key", "maize")
        name = _prompt_text(in_stream, out_stream, "Display name", "Maize (Zea mays)")
        values = _collect(_CROP_FIELDS, in_stream, out_stream)
        document = build_crop_document(key, name, values)
    else:
        key = _prompt_text(in_stream, out_stream, "Soil key", "loam")
        name = _prompt_text(in_stream, out_stream, "Display name", "Loam - Custom")
        values = _collect(_SOIL_FIELDS, in_stream, out_stream)
        document = build_soil_document(key, name, values)

    try:
        _validate_document(kind, document)
    except Exception as exc:  # - surface any validator failure
        out_stream.write(f"Validation failed; nothing written: {exc}\n")
        return 1

    _write_document(document, in_stream, out_stream)
    return 0
