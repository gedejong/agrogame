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
	# labor(50) + price_per_kg_nutrient * kg_nutrient, truncated (#508).
	# urea 1.47/kg N, ammonium_nitrate 3.63/kg N, tsp 4.73/kg P.
	assert_eq(FertilizerPicker.cost_for("urea", 50.0), 123)
	assert_eq(FertilizerPicker.cost_for("ammonium_nitrate", 50.0), 231)
	assert_eq(FertilizerPicker.cost_for("tsp", 50.0), 286)
	assert_eq(FertilizerPicker.cost_for("tsp", 100.0), 523)


# #465 lesson: the previewed cost must match the backend's int() truncation at
# a non-integral cost, not just at round numbers.
func test_cost_truncates_like_the_backend_at_a_non_integral_cost() -> void:
	# 50 + 1.47 * 50 = 123.5 exactly — truncates to 123, never rounds to 124.
	assert_eq(FertilizerPicker.cost_for("urea", 50.0), 123)
	# 50 + 4.73 * 25 = 168.25 — truncates to 168.
	assert_eq(FertilizerPicker.cost_for("tsp", 25.0), 168)


func test_cost_unknown_type_is_labor_only() -> void:
	# There is no per-kg fallback any more: the backend raises for an unpriced
	# type, so the picker must not invent a 1 cr/kg price either (#508).
	assert_eq(FertilizerPicker.cost_for("mystery", 50.0), 50)


# AC #2: rates and prices are per kg of nutrient element, and the label says so.
func test_nutrient_and_unit_name_the_element() -> void:
	assert_eq(FertilizerPicker.nutrient_for("urea"), "N")
	assert_eq(FertilizerPicker.nutrient_for("ammonium_nitrate"), "N")
	assert_eq(FertilizerPicker.nutrient_for("tsp"), "P")
	assert_eq(FertilizerPicker.nutrient_for("mystery"), "")
	assert_eq(FertilizerPicker.unit_for("urea"), "kg N/ha")
	assert_eq(FertilizerPicker.unit_for("tsp"), "kg P/ha")
	assert_eq(FertilizerPicker.unit_for("mystery"), "kg/ha")


func test_every_offered_type_is_priced_and_has_a_nutrient() -> void:
	for fert_type: String in FertilizerPicker.TYPES:
		assert_true(
			FertilizerPicker.PRICE_PER_KG_NUTRIENT.has(fert_type),
			"%s must have a per-kg-nutrient price" % fert_type
		)
		assert_false(FertilizerPicker.nutrient_for(fert_type).is_empty())


func test_label_shows_type_amount_and_cost() -> void:
	# TSP at first tier (25 kg P/ha) → 50 + 4.73*25 = 168.25 → 168 cr.
	var label: String = FertilizerPicker.label_for(2 * FertilizerPicker.AMOUNTS_KG_HA.size())
	assert_string_contains(label, "TSP")
	assert_string_contains(label, "25 kg P/ha")
	assert_string_contains(label, "168 cr")


func test_label_names_nitrogen_for_n_fertilizers() -> void:
	assert_string_contains(FertilizerPicker.label_for(0), "kg N/ha")
	assert_string_contains(
		FertilizerPicker.label_for(FertilizerPicker.AMOUNTS_KG_HA.size()), "kg N/ha"
	)


# #349 review: the Fertilize button gates on the cheapest tier, not urea-50.
func test_cheapest_option_is_lowest_cost() -> void:
	var cheapest: int = FertilizerPicker.cheapest_option_id()
	var cheapest_cost: int = FertilizerPicker.cost_for(
		FertilizerPicker.type_for(cheapest), FertilizerPicker.amount_for(cheapest)
	)
	# labor(50) + 1.47 * 25 = 86.75 → 86 for urea at the smallest tier (#508).
	assert_eq(cheapest_cost, 86, "cheapest tier costs 86 cr")
	for i in range(FertilizerPicker.option_count()):
		var cost: int = FertilizerPicker.cost_for(
			FertilizerPicker.type_for(i), FertilizerPicker.amount_for(i)
		)
		assert_true(cost >= cheapest_cost, "no option is cheaper than cheapest_option_id")


func test_is_affordable_reflects_option_cost() -> void:
	var cheapest: int = FertilizerPicker.cheapest_option_id()
	assert_true(FertilizerPicker.is_affordable(cheapest, 86), "exact cheapest balance affordable")
	assert_false(
		FertilizerPicker.is_affordable(cheapest, 85), "one short of cheapest not affordable"
	)
	# tsp at 100 kg P/ha = 50 + 4.73*100 = 523 cr (last option, type-major).
	var tsp_100: int = FertilizerPicker.option_count() - 1
	assert_false(FertilizerPicker.is_affordable(tsp_100, 100), "523 cr tier blocked at 100 cr")
	assert_true(FertilizerPicker.is_affordable(tsp_100, 523), "523 cr tier affordable at 523 cr")


func test_is_affordable_out_of_range_is_false() -> void:
	assert_false(FertilizerPicker.is_affordable(-1, 999999))
	assert_false(FertilizerPicker.is_affordable(FertilizerPicker.option_count(), 999999))


func test_starts_new_group_marks_type_boundaries() -> void:
	var n: int = FertilizerPicker.AMOUNTS_KG_HA.size()
	assert_false(FertilizerPicker.starts_new_group(0), "first option is not a boundary")
	assert_false(FertilizerPicker.starts_new_group(1))
	assert_true(FertilizerPicker.starts_new_group(n), "second type starts a group")
	assert_true(FertilizerPicker.starts_new_group(2 * n), "third type starts a group")
