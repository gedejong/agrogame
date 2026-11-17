extends GutTest

const LimePickerScript = preload("res://scripts/lime_picker.gd")


func test_script_loads() -> void:
	assert_not_null(LimePickerScript, "LimePicker script loads")


func test_tiers_are_in_tonnes_per_hectare() -> void:
	# AC #11: lime is offered in t/ha, not the 25/50/100 kg/ha fertiliser tiers.
	assert_eq(LimePicker.option_count(), LimePicker.AMOUNTS_T_HA.size())
	for i in range(LimePicker.option_count()):
		var t_ha: float = LimePicker.amount_t_ha_for(i)
		assert_true(t_ha >= 0.5 and t_ha <= 10.0, "tier %.1f t/ha is a sane lime rate" % t_ha)
		assert_eq(LimePicker.amount_kg_ha_for(i), t_ha * 1000.0, "kg/ha mirrors t/ha")


func test_out_of_range_options() -> void:
	assert_eq(LimePicker.amount_t_ha_for(-1), 0.0)
	assert_eq(LimePicker.amount_t_ha_for(LimePicker.option_count()), 0.0)
	assert_true(LimePicker.params_for(-1).is_empty())
	assert_eq(LimePicker.label_for(-1), "")
	assert_false(LimePicker.is_affordable(-1, 999999))
	assert_false(LimePicker.is_affordable(LimePicker.option_count(), 999999))


func test_params_use_kg_ha_and_target_topsoil() -> void:
	var params: Dictionary = LimePicker.params_for(0)
	assert_eq(params["amount_kg_ha"], 1000.0, "1.0 t/ha sends 1000 kg/ha")
	assert_eq(params["layer"], 0, "lime targets the topsoil by default")


# AC #4: a sub-1 credit/kg price must not truncate to zero.
func test_cost_matches_backend_float_formula() -> void:
	# labor(50) + 0.075 cr/kg * 1000 kg/ha = 125 cr, not 50 (int-truncated
	# per_kg) and not 1050 (per_kg rounded up to 1).
	assert_eq(LimePicker.cost_for(1000.0), 125)
	assert_eq(LimePicker.cost_for(2500.0), 238)
	assert_eq(LimePicker.cost_for(5000.0), 425)
	assert_eq(LimePicker.cost_for(0.0), 0, "a non-positive rate is free")


func test_cheapest_option_is_lowest_cost() -> void:
	var cheapest: int = LimePicker.cheapest_option_id()
	var cheapest_cost: int = LimePicker.cost_for(LimePicker.amount_kg_ha_for(cheapest))
	assert_eq(cheapest_cost, 125, "cheapest tier (1 t/ha) costs 125 cr")
	for i in range(LimePicker.option_count()):
		assert_true(
			LimePicker.cost_for(LimePicker.amount_kg_ha_for(i)) >= cheapest_cost,
			"no tier is cheaper than cheapest_option_id"
		)


func test_is_affordable_reflects_option_cost() -> void:
	var cheapest: int = LimePicker.cheapest_option_id()
	assert_true(LimePicker.is_affordable(cheapest, 125), "exact cheapest balance affordable")
	assert_false(LimePicker.is_affordable(cheapest, 124), "one short is not affordable")
	var dearest: int = LimePicker.option_count() - 1
	assert_false(LimePicker.is_affordable(dearest, 200), "5 t/ha blocked at 200 cr")
	assert_true(LimePicker.is_affordable(dearest, 425), "5 t/ha affordable at 425 cr")


func test_label_shows_rate_in_tonnes_and_cost() -> void:
	var label: String = LimePicker.label_for(1)
	assert_string_contains(label, "2.5 t/ha")
	assert_string_contains(label, "238 cr")
