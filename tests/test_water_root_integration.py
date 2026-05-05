from __future__ import annotations

from pathlib import Path

from agrogame.soil.loader import load_soil_presets
from agrogame.soil.water.models.cascading import CascadingBucketWaterModel
from agrogame.soil.water.state import SoilWaterState


def test_extract_transpiration_by_roots_respects_wilting_point() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    state = SoilWaterState(profile)
    model = CascadingBucketWaterModel()

    # Ensure top two layers have some water above wilting, others at wilting
    for i, layer in enumerate(profile.layers):
        target = layer.wilting_point
        if i == 0:
            target = min(layer.saturation, layer.wilting_point + 0.05)
        if i == 1:
            target = min(layer.saturation, layer.wilting_point + 0.03)
        # set theta directly by setting storage
        storage = target * layer.depth_cm * 10.0
        state.set_layer_storage_mm(profile, i, storage)

    demand = 10.0  # mm
    root_fracs = (0.7, 0.3, *tuple(0.0 for _ in range(len(profile.layers) - 2)))
    supplied = model.extract_transpiration_by_roots(profile, state, demand, root_fracs)

    # Available from layer 0 and 1 only
    avail0 = (
        (profile.layers[0].wilting_point + 0.05 - profile.layers[0].wilting_point)
        * profile.layers[0].depth_cm
        * 10.0
    )
    avail1 = (
        (profile.layers[1].wilting_point + 0.03 - profile.layers[1].wilting_point)
        * profile.layers[1].depth_cm
        * 10.0
    )
    expected = min(demand * 0.7, avail0) + min(demand * 0.3, avail1)
    assert abs(supplied - expected) < 1e-6


def test_extract_transpiration_zero_demand_and_empty_fractions() -> None:
    lib = load_soil_presets(Path("soils/presets.yaml"))
    profile = lib.soils["loam_temperate"]
    state = SoilWaterState(profile)
    model = CascadingBucketWaterModel()

    # Zero demand returns 0
    assert (
        model.extract_transpiration_by_roots(profile, state, 0.0, (1.0, 0.0, 0.0))
        == 0.0
    )

    # Empty fractions returns 0
    assert model.extract_transpiration_by_roots(profile, state, 5.0, ()) == 0.0
