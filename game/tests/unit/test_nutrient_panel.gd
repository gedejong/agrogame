extends GutTest

const NutrientPanel = preload("res://scripts/nutrient_panel.gd")


func test_nutrient_bars_defined() -> void:
	for key: String in ["NO₃", "NH₄", "P", "SOM", "Water", "pH", "Microbe", "MWD"]:
		assert_true(NutrientPanel.NUTRIENT_BARS.has(key), "Bar config for %s" % key)


func test_nutrient_bars_have_icon() -> void:
	for key: String in NutrientPanel.NUTRIENT_BARS:
		var cfg: Dictionary = NutrientPanel.NUTRIENT_BARS[key]
		assert_true(cfg.has("icon"), "%s has icon path" % key)


func test_stress_color_optimal() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 30.0, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_OK, "Optimal = green")


func test_stress_color_deficient() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 0.5, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Very low = red")


func test_stress_color_marginal() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 3.0, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_MARGINAL, "Low = yellow")


func test_stress_color_ph_extreme() -> void:
	var c: Color = NutrientPanel._stress_color("pH", 3.5, 5.5, 7.5)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Extreme pH = red")


func test_stress_color_ph_optimal() -> void:
	var c: Color = NutrientPanel._stress_color("pH", 6.5, 5.5, 7.5)
	assert_eq(c, NutrientPanel.BAR_OK, "Optimal pH = green")


func test_format_acceptor_all_values() -> void:
	assert_eq(NutrientPanel._format_acceptor("O2"), "O\u2082")
	assert_eq(NutrientPanel._format_acceptor("NO3"), "NO\u2083\u207b")
	assert_eq(NutrientPanel._format_acceptor("Fe3+"), "Fe\u00b3\u207a")
	assert_eq(NutrientPanel._format_acceptor("CH4"), "CH\u2084")


func test_format_acceptor_unknown() -> void:
	assert_eq(NutrientPanel._format_acceptor("Mn4+"), "Mn4+", "Unknown returns as-is")


func test_mwd_bar_stress_color_good() -> void:
	var c: Color = NutrientPanel._stress_color("MWD", 1.5, 1.0, 2.5)
	assert_eq(c, NutrientPanel.BAR_OK, "Good MWD = green")


func test_mwd_bar_stress_color_degraded() -> void:
	var c: Color = NutrientPanel._stress_color("MWD", 0.3, 1.0, 2.5)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Degraded MWD = red")
