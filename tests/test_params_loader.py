from agrogame.params.loader import load_library


def test_load_sample_params():
    lib = load_library("samples/crops.yaml")
    assert "maize" in lib.crops
    maize = lib.crops["maize"]
    assert maize.roots.max_depth_cm == 180
    assert abs(sum(maize.roots.distribution) - 1.0) < 1e-6


def test_other_crops_present():
    lib = load_library("samples/crops.yaml")
    assert set(["maize", "wheat", "potato"]).issubset(set(lib.crops.keys()))
    assert lib.crops["wheat"].thermal_time.base_temp_c == 0.0
    assert lib.crops["potato"].roots.max_depth_cm == 60
