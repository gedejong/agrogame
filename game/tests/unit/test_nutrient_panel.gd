extends GutTest

const NutrientPanel = preload("res://scripts/nutrient_panel.gd")


func test_nutrient_bars_defined() -> void:
	for key: String in ["NO₃", "NH₄", "P", "SOM", "θ", "pH", "Microbe"]:
		assert_true(NutrientPanel.NUTRIENT_BARS.has(key), "Bar config for %s" % key)


func test_stress_color_optimal() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 30.0, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_OK, "Optimal NO₃ = green")


func test_stress_color_deficient() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 0.5, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Very low NO₃ = red")


func test_stress_color_marginal() -> void:
	var c: Color = NutrientPanel._stress_color("NO₃", 3.0, 5.0, 60.0)
	assert_eq(c, NutrientPanel.BAR_MARGINAL, "Low NO₃ = yellow")


func test_stress_color_ph_extreme() -> void:
	var c: Color = NutrientPanel._stress_color("pH", 3.5, 5.5, 7.5)
	assert_eq(c, NutrientPanel.BAR_STRESS, "Extreme pH = red")


func test_stress_color_ph_optimal() -> void:
	var c: Color = NutrientPanel._stress_color("pH", 6.5, 5.5, 7.5)
	assert_eq(c, NutrientPanel.BAR_OK, "Optimal pH = green")
