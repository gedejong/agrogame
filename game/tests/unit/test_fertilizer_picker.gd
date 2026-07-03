extends GutTest

const FertilizerPickerScript = preload("res://scripts/fertilizer_picker.gd")


func test_script_loads() -> void:
	assert_not_null(FertilizerPickerScript, "FertilizerPicker script loads")


func test_types_cover_n_and_p() -> void:
	# AC #1: at least urea (N), ammonium_nitrate (N), tsp (P).
	assert_has(FertilizerPicker.TYPES, "urea")
	assert_has(FertilizerPicker.TYPES, "ammonium_nitrate")
	assert_has(FertilizerPicker.TYPES, "tsp")


func test_option_count() -> void:
	assert_eq(
		FertilizerPicker.option_count(),
		FertilizerPicker.TYPES.size() * FertilizerPicker.AMOUNTS_KG_HA.size(),
	)


func test_option_layout_is_type_major() -> void:
	# Options are laid out type-major: each type spans all amount tiers.
	var n: int = FertilizerPicker.AMOUNTS_KG_HA.size()
	assert_eq(FertilizerPicker.type_for(0), "urea")
	assert_eq(FertilizerPicker.type_for(n - 1), "urea")
	assert_eq(FertilizerPicker.type_for(n), "ammonium_nitrate")
	assert_eq(FertilizerPicker.type_for(2 * n), "tsp")


func test_amount_cycles_within_type() -> void:
	assert_eq(FertilizerPicker.amount_for(0), FertilizerPicker.AMOUNTS_KG_HA[0])
	assert_eq(FertilizerPicker.amount_for(1), FertilizerPicker.AMOUNTS_KG_HA[1])
	assert_eq(FertilizerPicker.amount_for(2), FertilizerPicker.AMOUNTS_KG_HA[2])


func test_option_out_of_range() -> void:
	assert_eq(FertilizerPicker.type_for(-1), "")
	assert_eq(FertilizerPicker.type_for(FertilizerPicker.option_count()), "")
	assert_eq(FertilizerPicker.amount_for(-1), 0.0)
	assert_eq(FertilizerPicker.amount_for(FertilizerPicker.option_count()), 0.0)
	assert_true(FertilizerPicker.params_for(-1).is_empty())
	assert_eq(FertilizerPicker.label_for(-1), "")


# Core AC #5: type selection maps to the correct execute_action params.
func test_selecting_tsp_yields_tsp_params() -> void:
	var n: int = FertilizerPicker.AMOUNTS_KG_HA.size()
	var params: Dictionary = FertilizerPicker.params_for(2 * n)
	assert_eq(params["type"], "tsp")
	assert_eq(params["amount_kg_ha"], FertilizerPicker.AMOUNTS_KG_HA[0])


func test_selecting_urea_yields_urea_params() -> void:
	var params: Dictionary = FertilizerPicker.params_for(1)
	assert_eq(params["type"], "urea")
	assert_eq(params["amount_kg_ha"], FertilizerPicker.AMOUNTS_KG_HA[1])


func test_selecting_ammonium_nitrate_yields_correct_params() -> void:
	var n: int = FertilizerPicker.AMOUNTS_KG_HA.size()
	var params: Dictionary = FertilizerPicker.params_for(n)
	assert_eq(params["type"], "ammonium_nitrate")
	assert_eq(params["amount_kg_ha"], FertilizerPicker.AMOUNTS_KG_HA[0])


# AC #3: cost reflects the chosen type — mirrors routes._compute_action_cost.
func test_cost_matches_backend_formula() -> void:
	# labor(50) + per_kg * amount. urea per_kg=1, tsp per_kg=2.
	assert_eq(FertilizerPicker.cost_for("urea", 50.0), 100)
	assert_eq(FertilizerPicker.cost_for("ammonium_nitrate", 50.0), 100)
	assert_eq(FertilizerPicker.cost_for("tsp", 50.0), 150)
	assert_eq(FertilizerPicker.cost_for("tsp", 100.0), 250)


func test_cost_unknown_type_defaults_per_kg_one() -> void:
	assert_eq(FertilizerPicker.cost_for("mystery", 50.0), 100)


func test_label_shows_type_amount_and_cost() -> void:
	# TSP at first amount tier (25 kg/ha) → 50 + 2*25 = 100 cr.
	var label: String = FertilizerPicker.label_for(2 * FertilizerPicker.AMOUNTS_KG_HA.size())
	assert_string_contains(label, "TSP")
	assert_string_contains(label, "25 kg/ha")
	assert_string_contains(label, "100 cr")


func test_starts_new_group_marks_type_boundaries() -> void:
	var n: int = FertilizerPicker.AMOUNTS_KG_HA.size()
	assert_false(FertilizerPicker.starts_new_group(0), "first option is not a boundary")
	assert_false(FertilizerPicker.starts_new_group(1))
	assert_true(FertilizerPicker.starts_new_group(n), "second type starts a group")
	assert_true(FertilizerPicker.starts_new_group(2 * n), "third type starts a group")
