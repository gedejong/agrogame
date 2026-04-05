extends GutTest

const SoilViewScript = preload("res://scripts/soil_view.gd")


func test_layer_colors_defined() -> void:
	assert_true(SoilViewScript.LAYER_COLORS.has("sand"))
	assert_true(SoilViewScript.LAYER_COLORS.has("loam"))
	assert_true(SoilViewScript.LAYER_COLORS.has("clay"))


func test_profile_layers_sandy() -> void:
	var layers: Array = SoilViewScript.get_profile_layers("sandy")
	assert_eq(layers.size(), 3, "Sandy has 3 layers")
	assert_eq(layers[0]["texture"], "sand")


func test_profile_layers_clay() -> void:
	var layers: Array = SoilViewScript.get_profile_layers("clay")
	assert_eq(layers.size(), 3, "Clay has 3 layers")
	assert_eq(layers[0]["texture"], "clay")


func test_profile_layers_organic() -> void:
	var layers: Array = SoilViewScript.get_profile_layers("organic")
	assert_eq(layers.size(), 3, "Organic/loam has 3 layers")
	assert_eq(layers[0]["texture"], "loam")


func test_constants() -> void:
	assert_gt(SoilViewScript.CUTAWAY_WIDTH, 0.0, "Cutaway width positive")
	assert_gt(SoilViewScript.SCALE_CM, 0.0, "Scale cm positive")
