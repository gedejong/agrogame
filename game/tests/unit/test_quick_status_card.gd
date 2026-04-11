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
		"som_total_c_g_m2": 1500.0,
		"theta_surface": 0.25,
	}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_gte(scores["water"], 90.0, "Healthy water")
	assert_gte(scores["nutrient"], 90.0, "Healthy nutrients")
	assert_gte(scores["growth"], 80.0, "Good growth")
	assert_gte(scores["soil"], 80.0, "Good soil (SOM=1500, theta=optimal)")


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
	assert_eq(scores["soil"], 25.0, "Bone dry theta=0 → theta_score=0, soil=SOM/2")


func test_theta_saturated() -> void:
	var data := {"theta_surface": 0.5, "som_total_c_g_m2": 1000.0, "crop_stage": 0}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_eq(scores["soil"], 25.0, "Saturated theta=0.5 → theta_score=0, soil=SOM/2")


func test_gauge_defs_count() -> void:
	assert_eq(QSC.GAUGE_DEFS.size(), 4, "4 health gauges")


func test_crop_max_lai_defined() -> void:
	assert_true(QSC.CROP_MAX_LAI.has("maize"), "Maize LAI defined")
	assert_true(QSC.CROP_MAX_LAI.has("spring_wheat"), "Wheat LAI defined")
	assert_lt(QSC.CROP_MAX_LAI["spring_wheat"], QSC.CROP_MAX_LAI["maize"], "Wheat LAI < maize LAI")
