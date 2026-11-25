extends GutTest
## Quick Status gauges, marks and advice (#660). Inputs are the tile keys
## FarmTiles.write_patch stores; the frames are the #660 refinement's (seed 42).

const QSC = preload("res://scripts/quick_status_card.gd")
## Just below, at and just above 40 and 70 (PR #673 review). The thresholds are
## strict, as ADR-017's drought alert is (Ks < 0.4): 40 reads "!", 70 no mark.
const BOUNDARY_SCORES: Array[float] = [39.9, 40.0, 40.1, 69.9, 70.0, 70.1]
const BOUNDARY_MARKS: Array[String] = ["⚠", "!", "!", "!", "", ""]


## A standing maize tile that needs nothing, with `extra` on top.
func _tile(stage: String, extra: Dictionary = {}) -> Dictionary:
	var tile := {
		"crop_key": "maize",
		"crop_stage_name": stage,
		"water_ks": 1.0,
		"growth_vs_potential": 1.0,
		"root_zone_water_fraction": 0.9,
		"depletion_fraction_p": 0.55,
	}
	tile.merge(extra, true)
	return tile


## Each gauge's [value, mark] as rendered, plus the advice line.
func _card(tile: Dictionary) -> Dictionary:
	var card: QuickStatusCard = QSC.new()
	add_child_autofree(card)
	card.show_status(tile, "Loam - Temperate")
	var out := {"advice": card._recommendation_label.text}
	for key: String in card._gauge_labels:
		var val: Label = card._gauge_labels[key]
		var row: Node = val.get_parent()
		var mark: String = ""
		if row.get_child_count() > 3:
			mark = (row.get_child(3) as Label).text.strip_edges()
		out[key] = [val.text, mark]
		out[key + "_tip"] = (row as Control).tooltip_text
	return out


func test_frame_nl_sandy_maize_day_21_reads_healthy() -> void:
	var g := _card(
		_tile(
			"vegetative",
			{
				"fe_stress": 0.09,
				"zn_stress": 0.106,
				"growth_vs_potential": 0.89,
				"root_zone_water_fraction": 0.866,
			}
		)
	)
	assert_eq(g["water"], ["100", ""])
	assert_eq(g["nutrient"], ["89", ""])
	assert_eq(g["growth"], ["89", ""])
	assert_eq(g["root_zone"], ["86", ""])
	assert_eq(g["advice"], "No action needed.")
	assert_string_ends_with(g["nutrient_tip"], "Limiting: zinc 0.89.")


func test_frame_sahel_maize_at_maturity_keeps_growth_without_marks() -> void:
	var tile := _tile("maturity", {"n_stress": 0.379, "growth_vs_potential": 0.042})
	tile["root_zone_water_fraction"] = 0.76
	var g := _card(tile)
	assert_eq(g["water"], ["—", ""])
	assert_eq(g["nutrient"], ["—", ""])
	assert_eq(g["growth"], ["4", ""])
	assert_eq(g["root_zone"], ["76", ""])
	assert_eq(g["advice"], "Mature: ready to harvest.")


func test_frame_kenya_rice_field_2_day_120_is_short_of_water() -> void:
	var tile := _tile("grain_fill", {"crop_key": "rice", "water_ks": 0.0, "n_stress": 0.369})
	tile.merge(
		{
			"growth_vs_potential": 0.499,
			"root_zone_water_fraction": 0.0,
			"depletion_fraction_p": 0.2
		},
		true
	)
	var g := _card(tile)
	assert_eq(g["water"], ["0", "⚠"])
	assert_eq(g["nutrient"], ["63", "!"])
	assert_eq(g["growth"], ["49", "!"])
	assert_eq(g["root_zone"], ["0", "!"])
	assert_eq(g["advice"], "Crop is short of water. Irrigate now.")
	assert_string_ends_with(g["nutrient_tip"], "Limiting: nitrogen 0.63.")


func test_peat_root_zone_caps_at_100_without_mark() -> void:
	# Replaces test_theta_saturated: a wet profile reads full, never "off optimum".
	assert_eq(
		_card(_tile("vegetative", {"root_zone_water_fraction": 1.3}))["root_zone"], ["100", ""]
	)


func test_root_zone_mark_follows_the_crops_p() -> void:
	# Replaces test_theta_bone_dry. At 0.75 of TAW rice (p 0.20) has used its
	# readily available water and maize (p 0.55) has not (FAO-56 Table 22).
	var rice := _tile("vegetative", {"crop_key": "rice", "depletion_fraction_p": 0.2})
	rice["root_zone_water_fraction"] = 0.75
	var maize := _tile("vegetative", {"root_zone_water_fraction": 0.75})
	assert_eq(_card(rice)["root_zone"], ["75", "!"])
	assert_eq(_card(maize)["root_zone"], ["75", ""])
	var dry := _card(_tile("vegetative", {"root_zone_water_fraction": 0.0}))
	assert_eq(dry["root_zone"], ["0", "!"], "never ⚠: red stays with Water")
	assert_eq(dry["advice"], "Root zone is drying. Irrigate before the crop shows stress.")


func test_bare_and_unemerged_tiles_show_dashes() -> void:
	var bare := _card({"crop_key": "", "root_zone_water_fraction": 0.6})
	for key: String in ["water", "nutrient", "growth"]:
		assert_eq(bare[key], ["—", ""], key)
	assert_eq(bare["root_zone"], ["60", ""])
	assert_eq(bare["advice"], "No crop planted. Consider planting.")
	var sown := _card(
		_tile("planted", {"growth_vs_potential": -1.0, "root_zone_water_fraction": 0.2})
	)
	assert_eq(
		[sown["water"], sown["growth"], sown["root_zone"]], [["—", ""], ["—", ""], ["20", ""]]
	)
	assert_eq(sown["advice"], "Sown, not yet emerged.")
	assert_eq(_card({"crop_key": ""})["root_zone"], ["—", ""], "no reply yet")


func test_growth_reads_biomass_against_potential_not_lai() -> void:
	# Replaces test_compute_scores_wheat_lai: LAI is not an input.
	var tile := _tile("vegetative", {"crop_key": "spring_wheat", "growth_vs_potential": 0.5})
	for lai: float in [0.1, 2.8, 6.0]:
		tile["lai"] = lai
		assert_eq(QSC.compute_scores(tile)["growth"], 50.0)
	var g := _card(tile)
	assert_eq(g["growth"], ["50", "!"])
	assert_eq(g["advice"], "Growth is behind its potential after earlier stress or damage.")
	assert_eq(_card(_tile("vegetative", {"growth_vs_potential": 0.39}))["growth"], ["39", "⚠"])


func test_n_mark_and_advice_follow_the_alerts_stage_gate() -> void:
	var veg := _card(_tile("vegetative", {"n_stress": 0.15}))
	assert_eq(veg["nutrient"], ["85", "!"])
	assert_eq(veg["advice"], "Nitrogen is limiting growth. Apply urea or ammonium nitrate.")
	var fill := _card(_tile("grain_fill", {"n_stress": 0.15}))
	assert_eq(fill["nutrient"], ["85", ""])
	assert_eq(fill["advice"], "No action needed.")
	var late := _card(_tile("grain_fill", {"n_stress": 0.5}))
	assert_eq(
		late["advice"], "Nitrogen is limiting growth, but fertilizer this late adds little yield."
	)


func test_each_nutrient_names_itself() -> void:
	var expected := {
		"p_stress": "Phosphorus is limiting growth. Apply TSP.",
		"s_stress": "Sulfur is limiting growth.",
		"fe_stress": "Iron is limiting growth.",
		"zn_stress": "Zinc is limiting growth.",
		"mn_stress": "Manganese is limiting growth.",
	}
	for key: String in expected:
		var g := _card(_tile("vegetative", {key: 0.51}))
		assert_eq(g["advice"], expected[key], key)
		assert_eq(g["nutrient"], ["49", "!"], key)


func test_water_against_nitrogen_the_lower_names_the_limit() -> void:
	var water := _tile("vegetative", {"water_ks": 0.35, "n_stress": 0.59})
	assert_eq(QSC.compute_recommendation(water), "Crop is short of water. Irrigate now.")
	var tie := _tile("vegetative", {"water_ks": 0.5, "n_stress": 0.5})
	assert_eq(
		QSC.compute_recommendation(tie),
		"Crop is starting to run short of water. Consider irrigating.",
		"a tie goes to water"
	)
	var nitrogen := _tile("vegetative", {"water_ks": 0.6, "n_stress": 0.59})
	assert_string_starts_with(QSC.compute_recommendation(nitrogen), "Nitrogen is limiting")


func test_limiting_text_reads_none_on_an_unlimited_crop() -> void:
	assert_eq(QSC.limiting_text(_tile("vegetative")), "Limiting: none.")


func test_value_colour_follows_the_mark() -> void:
	assert_eq(QSC._value_color("⚠", true), UiTheme.ACCENT_RED)
	assert_eq(QSC._value_color("!", true), UiTheme.ACCENT_GOLD)
	assert_eq(QSC._value_color("", true), UiTheme.ACCENT_GREEN)
	assert_eq(QSC._value_color("", false), UiTheme.TEXT_SECONDARY, "off season: neutral")


func test_near_one_ks_reads_100_not_99() -> void:
	# The engine's Ks of an unstressed day is 0.9999999999999998.
	assert_eq(_card(_tile("vegetative", {"water_ks": 0.9999999999999998}))["water"], ["100", ""])


func test_marks_pin_the_40_and_70_boundaries() -> void:
	var tile := _tile("vegetative")
	for key: String in ["water", "nutrient", "growth"]:
		for i: int in BOUNDARY_SCORES.size():
			var scores := {"water": 100.0, "nutrient": 100.0, "growth": 100.0, "root_zone": 90.0}
			scores[key] = BOUNDARY_SCORES[i]
			var why := "%s at %s" % [key, BOUNDARY_SCORES[i]]
			assert_eq(QSC.gauge_mark(key, tile, scores), BOUNDARY_MARKS[i], why)


func test_boundary_marks_from_the_engine_fractions() -> void:
	# The same six points as the /step fields arrive: Ks, growth and the Liebig
	# minimum (P here, clear of the N alert's own 0.90 gate) as fractions.
	var inputs := {
		"water": ["water_ks", [0.399, 0.40, 0.401, 0.699, 0.70, 0.701]],
		"growth": ["growth_vs_potential", [0.399, 0.40, 0.401, 0.699, 0.70, 0.701]],
		"nutrient": ["p_stress", [0.601, 0.60, 0.599, 0.301, 0.30, 0.299]],
	}
	for key: String in inputs:
		var field: String = inputs[key][0]
		var values: Array = inputs[key][1]
		for i: int in values.size():
			var tile := _tile("vegetative", {field: values[i]})
			var why := "%s %s" % [field, values[i]]
			assert_eq(QSC.gauge_mark(key, tile, QSC.compute_scores(tile)), BOUNDARY_MARKS[i], why)
	var shown := [["39", "⚠"], ["40", "!"], ["40", "!"], ["69", "!"], ["70", ""], ["70", ""]]
	var ks: Array = inputs["water"][1]
	for i: int in ks.size():
		assert_eq(_card(_tile("vegetative", {"water_ks": ks[i]}))["water"], shown[i], str(ks[i]))


func test_uncited_references_are_gone() -> void:
	# Replaces test_crop_max_lai_defined (C5).
	var consts: Dictionary = (QSC as Script).get_script_constant_map()
	for name: String in ["CROP_MAX_LAI", "THETA_OPTIMAL", "THETA_RANGE"]:
		assert_false(consts.has(name), name)
	var methods: Array = (QSC as Script).get_script_method_list().map(
		func(m: Dictionary) -> String: return m["name"]
	)
	assert_does_not_have(methods, "_expected_lai_for_stage")


func test_gauge_defs_count_and_tooltips() -> void:
	assert_eq(QSC.GAUGE_DEFS.size(), 4, "4 health gauges")
	for def: Dictionary in QSC.GAUGE_DEFS:
		assert_false(String(def["tip"]).is_empty(), def["key"])


func test_advised_nutrient_is_the_one_the_advice_acts_on() -> void:
	# #669: the stress icons draw this nutrient's icon. "" unless the advised
	# gauge is Nutrients: water first (Ks 0.32 below N 0.6), mature, root zone.
	assert_eq(QSC.advised_nutrient(_tile("vegetative", {"s_stress": 0.48})), "sulfur")
	assert_eq(QSC.advised_nutrient(_tile("vegetative", {"n_stress": 0.2})), "nitrogen")
	assert_eq(QSC.advised_nutrient(_tile("grain_fill", {"n_stress": 0.2})), "")
	assert_eq(QSC.advised_nutrient(_tile("vegetative", {"water_ks": 0.32, "n_stress": 0.4})), "")
	assert_eq(QSC.advised_nutrient(_tile("maturity", {"n_stress": 0.74})), "")
	assert_eq(QSC.advised_nutrient(_tile("vegetative", {"root_zone_water_fraction": 0.4})), "")
