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


def test_every_preset_specifies_literature_grounded_topsoil_sulfur() -> None:
    """Each preset must set initial_s_kg_ha to a literature-grounded value.

    Rather than relying on the SoilLayer default (which would leave S as an
    unset-field artifact), every soil preset declares plant-available sulfate-S
    per layer. Expressed as a concentration, topsoil available SO4-S should land
    in the adequate 8-20 mg/kg band for unfertilized agricultural soils and
    decline with depth (Eriksen 2009, Adv. Agron. 102; Scherer 2001, Eur. J.
    Agron. 14:81-111). Concentration = kg/ha / (bulk_density * depth_cm * 0.1).
    """
    lib = load_soil_presets(Path("soils/presets.yaml"))
    for name, profile in lib.soils.items():
        concentrations: list[float] = []
        for layer in profile.layers:
            # Every layer must set S explicitly, not fall back to the default.
            assert layer.initial_s_kg_ha > 0.0, f"{name}: unset layer S"
            conc = layer.initial_s_kg_ha / (
                layer.bulk_density_g_cm3 * layer.depth_cm * 0.1
            )
            concentrations.append(conc)
        topsoil = concentrations[0]
        assert 8.0 <= topsoil <= 20.0, f"{name}: topsoil {topsoil:.1f} mg/kg S"
        # Available SO4-S concentration should not increase with depth.
        assert concentrations[-1] <= topsoil, f"{name}: subsoil S exceeds topsoil"
