extends GutTest

const SU = preload("res://scripts/stress_utils.gd")


func test_parse_stress_data_all_zeros() -> void:
	var data: Dictionary = {}
	var result: Dictionary = SU.parse_stress_data(data)
	assert_eq(result["water"], 0.0, "No water stress data = 0")
	assert_eq(result["n"], 0.0, "No N stress data = 0")
	assert_eq(result["p"], 0.0, "No P stress data = 0")
	assert_eq(result["fe"], 0.0, "No Fe stress data = 0")
	assert_eq(result["zn"], 0.0, "No Zn stress data = 0")


func test_parse_stress_data_water_stress() -> void:
	var data := {"water_stress": 0.3}
	var result: Dictionary = SU.parse_stress_data(data)
	assert_almost_eq(result["water"], 0.7, 0.01, "water_stress 0.3 → stress 0.7")


func test_parse_stress_data_multiple_stresses() -> void:
	var data := {"water_stress": 0.5, "n_stress": 0.8, "fe_stress": 0.4}
	var result: Dictionary = SU.parse_stress_data(data)
	assert_almost_eq(result["water"], 0.5, 0.01, "Water stress 0.5")
	assert_almost_eq(result["n"], 0.8, 0.01, "N stress 0.8")
	assert_almost_eq(result["fe"], 0.4, 0.01, "Fe stress 0.4")
	assert_eq(result["p"], 0.0, "P not set = 0")
	assert_eq(result["zn"], 0.0, "Zn not set = 0")


func test_dominant_stress_returns_highest() -> void:
	var stresses := {"water": 0.2, "n": 0.8, "p": 0.1, "fe": 0.3, "zn": 0.0}
	var result: String = SU.dominant_stress(stresses)
	assert_eq(result, "n", "Highest stress is N")


func test_dominant_stress_tie_breaking() -> void:
	var stresses := {"water": 0.5, "n": 0.5, "p": 0.0, "fe": 0.0, "zn": 0.0}
	var result: String = SU.dominant_stress(stresses)
	assert_eq(result, "water", "Tie broken by STRESS_KEYS order (water first)")


func test_parse_clamps_values() -> void:
	var data := {"water_stress": -0.5, "n_stress": 2.0}
	var result: Dictionary = SU.parse_stress_data(data)
	assert_eq(result["water"], 1.0, "Negative water_stress → 1.0 stress (clamped)")
	assert_eq(result["n"], 1.0, "n_stress > 1.0 clamped to 1.0")


func test_stress_keys_constant() -> void:
	assert_eq(SU.STRESS_KEYS.size(), 5, "5 stress types defined")
	assert_has(SU.STRESS_KEYS, "water")
	assert_has(SU.STRESS_KEYS, "n")
	assert_has(SU.STRESS_KEYS, "p")
	assert_has(SU.STRESS_KEYS, "fe")
	assert_has(SU.STRESS_KEYS, "zn")
