extends GutTest

const QSC = preload("res://scripts/quick_status_card.gd")


func test_compute_scores_healthy() -> void:
	var data := {
		"water_stress": 1.0,
		"n_stress": 0.0,
		"p_stress": 0.0,
		"fe_stress": 0.0,
		"zn_stress": 0.0,
		"lai": 4.0,
		"crop_stage": 2,
		"crop_key": "maize",
		"theta_surface": 0.25,
	}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_gte(scores["water"], 90.0, "Healthy water")
	assert_gte(scores["nutrient"], 90.0, "Healthy nutrients")
	assert_gte(scores["growth"], 80.0, "Good growth")
	assert_gte(scores["soil"], 80.0, "Good soil moisture (theta=optimal)")


func test_compute_scores_drought() -> void:
	var data := {"water_stress": 0.3, "crop_stage": 2, "lai": 2.0}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_lt(scores["water"], 40.0, "Drought = low water score")


func test_compute_scores_n_deficiency() -> void:
	var data := {"water_stress": 1.0, "n_stress": 0.8, "crop_stage": 2, "lai": 2.0}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_lt(scores["nutrient"], 30.0, "N deficiency = low nutrient score")


func test_compute_scores_no_crop() -> void:
	var data := {"crop_stage": 0}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_eq(scores["growth"], 100.0, "No crop = growth 100 (N/A)")


func test_compute_scores_wheat_lai() -> void:
	# Wheat max LAI ~4.0. At stage 2, expected = 4.0 * 0.7 = 2.8.
	# LAI 2.8 should be ~100% growth.
	var data := {"crop_stage": 2, "crop_key": "spring_wheat", "lai": 2.8}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_gte(scores["growth"], 90.0, "Wheat at expected LAI = high growth")


func test_recommendation_no_crop() -> void:
	var data := {"crop_key": ""}
	var scores := {"water": 100.0, "nutrient": 100.0, "growth": 100.0, "soil": 100.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "planting")


func test_recommendation_drought() -> void:
	var data := {"crop_key": "maize", "water_stress": 0.2}
	var scores := {"water": 20.0, "nutrient": 90.0, "growth": 80.0, "soil": 70.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "irrigat")


func test_recommendation_n_deficiency() -> void:
	var data := {"crop_key": "maize", "n_stress": 0.5}
	var scores := {"water": 90.0, "nutrient": 30.0, "growth": 80.0, "soil": 70.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "fertiliz")


func test_recommendation_p_deficiency() -> void:
	var data := {"crop_key": "maize", "p_stress": 0.5, "n_stress": 0.0}
	var scores := {"water": 90.0, "nutrient": 30.0, "growth": 80.0, "soil": 70.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "TSP")


func test_recommendation_micronutrient() -> void:
	var data := {"crop_key": "maize", "fe_stress": 0.5, "n_stress": 0.0, "p_stress": 0.0}
	var scores := {"water": 90.0, "nutrient": 30.0, "growth": 80.0, "soil": 70.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "icronutrient")


func test_recommendation_healthy() -> void:
	var data := {"crop_key": "maize"}
	var scores := {"water": 90.0, "nutrient": 85.0, "growth": 80.0, "soil": 75.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "healthy")


func test_score_color_green() -> void:
	assert_eq(QSC._score_color(80.0), UiTheme.ACCENT_GREEN, "Score >70 = green")


func test_score_color_yellow() -> void:
	assert_eq(QSC._score_color(55.0), UiTheme.ACCENT_GOLD, "Score 40-70 = yellow")


func test_score_color_red() -> void:
	assert_eq(QSC._score_color(20.0), UiTheme.ACCENT_RED, "Score <40 = red")


func test_score_color_at_boundary_70() -> void:
	assert_eq(QSC._score_color(70.0), UiTheme.ACCENT_GREEN, "Exactly 70 = green")


func test_score_color_at_boundary_40() -> void:
	assert_eq(QSC._score_color(40.0), UiTheme.ACCENT_GOLD, "Exactly 40 = yellow")


func test_theta_bone_dry() -> void:
	var data := {"theta_surface": 0.0, "som_total_c_g_m2": 1000.0, "crop_stage": 0}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_eq(scores["soil"], 0.0, "Bone dry theta=0 scores 0, whatever the SOM")


func test_theta_saturated() -> void:
	var data := {"theta_surface": 0.5, "som_total_c_g_m2": 1000.0, "crop_stage": 0}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_eq(scores["soil"], 0.0, "Saturated theta=0.5 scores 0, whatever the SOM")


func test_soil_gauge_ignores_som_and_follows_theta() -> void:
	# #629: the SOM term is gone, so it neither saturates nor moves the gauge;
	# theta moves it by 20% around a typical value.
	var base := {"theta_surface": 0.2, "crop_stage": 0}
	var low: float = QSC.compute_scores(base)["soil"]
	for som: float in [0.0, 7345.0, 73450.0]:
		base["som_total_c_g_m2"] = som
		assert_eq(QSC.compute_scores(base)["soil"], low, "SOM %.0f is not an input" % som)
	var wetter: float = QSC.compute_scores({"theta_surface": 0.24, "crop_stage": 0})["soil"]
	var drier: float = QSC.compute_scores({"theta_surface": 0.16, "crop_stage": 0})["soil"]
	assert_gt(wetter, low, "+20% theta moves the gauge")
	assert_lt(drier, low, "-20% theta moves the gauge")
	assert_lt(low, 100.0, "no saturation at a typical theta")


func test_soil_gauge_is_labelled_for_what_it_measures() -> void:
	var labels: Array = QSC.GAUGE_DEFS.map(func(g: Dictionary) -> String: return g["label"])
	assert_has(labels, "Soil moisture")
	assert_does_not_have(labels, "Soil")


func test_card_title_uses_the_given_soil_name() -> void:
	var card := QSC.new()
	add_child_autofree(card)
	card.show_status({"crop_key": "maize", "crop_stage": 0}, "Loam - Temperate")
	assert_eq(card._tile_label.text, "Maize — Loam - Temperate")


func test_gauge_defs_count() -> void:
	assert_eq(QSC.GAUGE_DEFS.size(), 4, "4 health gauges")


func test_crop_max_lai_defined() -> void:
	assert_true(QSC.CROP_MAX_LAI.has("maize"), "Maize LAI defined")
	assert_true(QSC.CROP_MAX_LAI.has("spring_wheat"), "Wheat LAI defined")
	assert_lt(QSC.CROP_MAX_LAI["spring_wheat"], QSC.CROP_MAX_LAI["maize"], "Wheat LAI < maize LAI")
