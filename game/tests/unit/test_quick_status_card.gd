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
		"som_total_c_g_m2": 1500.0,
		"theta_surface": 0.25
	}
	var scores: Dictionary = QSC.compute_scores(data)
	assert_gte(scores["water"], 90.0, "Healthy water")
	assert_gte(scores["nutrient"], 90.0, "Healthy nutrients")
	assert_gte(scores["growth"], 80.0, "Good growth")
	assert_gt(scores["soil"], 30.0, "Reasonable soil")


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


func test_recommendation_healthy() -> void:
	var data := {"crop_key": "maize"}
	var scores := {"water": 90.0, "nutrient": 85.0, "growth": 80.0, "soil": 75.0}
	var rec: String = QSC.compute_recommendation(data, scores)
	assert_string_contains(rec, "healthy")


func test_score_color_green() -> void:
	var c: Color = QSC._score_color(80.0)
	assert_eq(c, UiTheme.ACCENT_GREEN, "Score >=70 = green")


func test_score_color_yellow() -> void:
	var c: Color = QSC._score_color(55.0)
	assert_eq(c, UiTheme.ACCENT_GOLD, "Score 40-70 = yellow")


func test_score_color_red() -> void:
	var c: Color = QSC._score_color(20.0)
	assert_eq(c, UiTheme.ACCENT_RED, "Score <40 = red")


func test_gauge_defs_count() -> void:
	assert_eq(QSC.GAUGE_DEFS.size(), 4, "4 health gauges")
