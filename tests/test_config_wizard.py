from __future__ import annotations

import io
from pathlib import Path


from agrogame.config.validation import validate_data
from agrogame.config.wizard import (
    FieldSpec,
    build_crop_document,
    build_soil_document,
    run_wizard,
)
from agrogame.plant.presets import load_crop_presets
from agrogame.soil.models import SoilLibrary


def _run(script: str) -> tuple[int, str, io.StringIO]:
    out = io.StringIO()
    code = run_wizard(io.StringIO(script), out)
    return code, out.getvalue(), out


def _soil_defaults_script(out_path: Path) -> str:
    # kind, soil key, name, then 9 blank soil fields, then output path.
    return "soil\n\n\n" + "\n" * 9 + f"{out_path}\n"


def _crop_defaults_script(out_path: Path) -> str:
    # kind, crop key, name, then 12 blank crop fields, then output path.
    return "crop\n\n\n" + "\n" * 12 + f"{out_path}\n"


def test_hint_string_shows_unit_range_and_default() -> None:
    spec = FieldSpec(
        ("phenology", "base_temperature_c"), "base_temp_c", "degC", 0, 15, 8.0
    )
    assert spec.hint() == "base_temp_c [0-15 degC, default 8.0]: "


def test_soil_path_writes_valid_runtime_shape(tmp_path: Path) -> None:
    out_path = tmp_path / "soil.yaml"
    code, out, _ = _run(_soil_defaults_script(out_path))

    assert code == 0
    assert out_path.exists()
    assert f"Wrote {out_path}" in out

    import yaml

    data = yaml.safe_load(out_path.read_text())
    # Emits the data/soils/presets.yaml shape.
    assert "soils" in data and "loam" in data["soils"]
    assert data["soils"]["loam"]["layers"][0]["texture"] == "loam"
    # Full-document validation both ways.
    validate_data(data, "soil")
    lib = SoilLibrary.model_validate(data)
    assert lib.soils["loam"].name == "Loam - Custom"


def test_crop_path_loads_via_load_crop_presets(tmp_path: Path) -> None:
    out_path = tmp_path / "crop.yaml"
    code, _out, _ = _run(_crop_defaults_script(out_path))

    assert code == 0
    import yaml

    data = yaml.safe_load(out_path.read_text())
    # Runtime crop shape, not the stale crop.json shape.
    body = data["crops"]["maize"]
    assert set(body) >= {"name", "phenology", "canopy", "roots"}
    assert "thermal_time" not in body and "biomass" not in body
    # Loads through the runtime loader without error.
    lib = load_crop_presets(out_path)
    preset = lib.get_preset("maize")
    assert preset.phenology.base_temperature_c == 8.0
    assert preset.canopy.lai_max == 6.0


def test_out_of_range_input_is_reprompted_then_accepted(tmp_path: Path) -> None:
    out_path = tmp_path / "crop.yaml"
    # base_temp_c: first 99 (out of 0-15) -> rejected, then 6.5 accepted.
    script = "crop\n\n\n" + "99\n6.5\n" + "\n" * 11 + f"{out_path}\n"
    code, out, _ = _run(script)

    assert code == 0
    assert "out of range" in out
    import yaml

    data = yaml.safe_load(out_path.read_text())
    assert data["crops"]["maize"]["phenology"]["base_temperature_c"] == 6.5


def test_non_numeric_input_is_reprompted(tmp_path: Path) -> None:
    out_path = tmp_path / "crop.yaml"
    script = "crop\n\n\n" + "abc\n7\n" + "\n" * 11 + f"{out_path}\n"
    code, out, _ = _run(script)

    assert code == 0
    assert "is not a number" in out


def test_declining_overwrite_leaves_original_untouched(tmp_path: Path) -> None:
    out_path = tmp_path / "soil.yaml"
    out_path.write_text("original: content\n")
    # decline the overwrite confirmation (blank -> N).
    script = _soil_defaults_script(out_path) + "n\n"
    code, out, _ = _run(script)

    assert code == 0
    assert "Left existing file untouched" in out
    assert out_path.read_text() == "original: content\n"


def test_accepting_overwrite_replaces_file(tmp_path: Path) -> None:
    out_path = tmp_path / "soil.yaml"
    out_path.write_text("original: content\n")
    script = _soil_defaults_script(out_path) + "y\n"
    code, out, _ = _run(script)

    assert code == 0
    assert f"Wrote {out_path}" in out
    assert "soils" in out_path.read_text()


def test_empty_output_path_aborts_without_writing(tmp_path: Path) -> None:
    # Supply an empty output path (blank line at the prompt).
    script = "soil\n\n\n" + "\n" * 9 + "\n"
    code, out, _ = _run(script)

    assert code == 0
    assert "No path given" in out


def test_choice_reprompts_on_invalid_kind(tmp_path: Path) -> None:
    out_path = tmp_path / "soil.yaml"
    script = "banana\n" + _soil_defaults_script(out_path)
    code, out, _ = _run(script)

    assert code == 0
    assert "choose one of crop/soil" in out
    assert out_path.exists()


def test_build_soil_document_applies_values_to_all_layers() -> None:
    doc = build_soil_document("mysoil", "My Soil", {("organic_matter_pct",): 3.3})
    layers = doc["soils"]["mysoil"]["layers"]
    assert all(layer["organic_matter_pct"] == 3.3 for layer in layers)


def test_build_crop_document_sets_nested_path() -> None:
    doc = build_crop_document("maize", "Maize", {("canopy", "lai_max"): 5.0})
    assert doc["crops"]["maize"]["canopy"]["lai_max"] == 5.0
