from __future__ import annotations

from pathlib import Path

from agrogame.soil.loader import load_soil_presets


def test_load_soil_presets_minimums() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    assert "sandy_arid" in lib.soils
    assert "loam_temperate" in lib.soils
    assert "clay_temperate" in lib.soils

    for profile in lib.soils.values():
        # At least 3 layers and total depth >= 100 cm per model constraints
        assert len(profile.layers) >= 3
        total_depth = sum(layer.depth_cm for layer in profile.layers)
        assert total_depth >= 100.0
        for layer in profile.layers:
            assert (
                0.0
                <= layer.wilting_point
                < layer.field_capacity
                < layer.saturation
                <= 0.8
            )
            assert layer.bulk_density_g_cm3 > 0
            assert layer.ksat_mm_per_hour > 0
