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
	assert_eq(SU.STRESS_KEYS.size(), 7, "7 stress types defined")
	assert_has(SU.STRESS_KEYS, "water")
	assert_has(SU.STRESS_KEYS, "n")
	assert_has(SU.STRESS_KEYS, "p")
	assert_has(SU.STRESS_KEYS, "fe")
	assert_has(SU.STRESS_KEYS, "zn")
	assert_has(SU.STRESS_KEYS, "frost")
	assert_has(SU.STRESS_KEYS, "heat")


func test_parse_frost_and_heat() -> void:
	var data := {"frost_damage": 0.6, "heat_damage": 0.4}
	var result: Dictionary = SU.parse_stress_data(data)
	assert_almost_eq(result["frost"], 0.6, 0.01, "Frost damage parsed")
	assert_almost_eq(result["heat"], 0.4, 0.01, "Heat damage parsed")


func test_parse_frost_heat_default_zero() -> void:
	var result: Dictionary = SU.parse_stress_data({})
	assert_eq(result["frost"], 0.0, "Frost defaults to 0")
	assert_eq(result["heat"], 0.0, "Heat defaults to 0")


func test_calc_stunt_factor_no_stress() -> void:
	var s: float = SU.calc_stunt_factor({"zn": 0.0})
	assert_eq(s, 1.0, "No Zn stress = full size")


func test_calc_stunt_factor_severe_zn() -> void:
	var s: float = SU.calc_stunt_factor({"zn": 1.0})
	assert_almost_eq(s, 0.7, 0.01, "Severe Zn = 30% reduction")


func test_calc_stunt_factor_partial_zn() -> void:
	var s: float = SU.calc_stunt_factor({"zn": 0.5})
	assert_almost_eq(s, 0.85, 0.01, "Half Zn = 15% reduction")


func test_calc_collapse_factor_healthy() -> void:
	assert_eq(SU.calc_collapse_factor(0.0), 1.0, "No senescence = full height")
	assert_eq(SU.calc_collapse_factor(0.84), 1.0, "Below collapse threshold = full height")


func test_calc_collapse_factor_dead() -> void:
	assert_almost_eq(SU.calc_collapse_factor(1.0), 0.4, 0.01, "Fully senesced = collapsed")


func test_calc_collapse_factor_partial() -> void:
	# At sen=0.925 (midway between 0.85 and 1.0), Y scale = lerp(1.0, 0.4, 0.5) = 0.7
	assert_almost_eq(SU.calc_collapse_factor(0.925), 0.7, 0.01, "Half collapse at sen 0.925")
