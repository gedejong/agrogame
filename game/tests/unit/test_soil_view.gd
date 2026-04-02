extends GutTest
## Tests for the inline 2D soil cross-section view.

const SoilView = preload("res://scripts/soil_view.gd")


func test_layer_colors_defined() -> void:
	assert_true(SoilView.LAYER_COLORS.has("sand"), "Sand color defined")
	assert_true(SoilView.LAYER_COLORS.has("clay"), "Clay color defined")
	assert_true(SoilView.LAYER_COLORS.has("loam"), "Loam color defined")
	assert_true(SoilView.LAYER_COLORS.has("peat"), "Peat color defined")


func test_sand_lighter_than_clay() -> void:
	var sand: Color = SoilView.LAYER_COLORS["sand"]
	var clay: Color = SoilView.LAYER_COLORS["clay"]
	assert_true(sand.v > clay.v, "Sand should be lighter than clay")


func test_nutrient_colors_distinct() -> void:
	assert_true(
		SoilView.N_COLOR.g > SoilView.N_COLOR.r,
		"N color should be greenish",
	)
	assert_true(
		SoilView.P_COLOR.b > SoilView.P_COLOR.g,
		"P color should be purplish",
	)


func test_cutaway_dimensions_positive() -> void:
	assert_true(SoilView.HALF_W > 0, "Half width positive")
	assert_true(SoilView.HALF_H > 0, "Half height positive")
	assert_true(SoilView.DEPTH_SCALE > 0, "Depth scale positive")
