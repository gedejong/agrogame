extends GutTest

const SoilView3DScript = preload("res://scripts/soil_view_3d.gd")


func test_layer_colors_defined() -> void:
	assert_true(SoilView3DScript.LAYER_COLORS.has("sand"))
	assert_true(SoilView3DScript.LAYER_COLORS.has("loam"))
	assert_true(SoilView3DScript.LAYER_COLORS.has("clay"))


func test_profile_layers_sandy() -> void:
	var layers: Array = SoilView3DScript.get_profile_layers("sandy")
	assert_eq(layers.size(), 3, "Sandy has 3 layers")
	assert_eq(layers[0]["texture"], "sand")


func test_profile_layers_clay() -> void:
	var layers: Array = SoilView3DScript.get_profile_layers("clay")
	assert_eq(layers.size(), 3, "Clay has 3 layers")
	assert_eq(layers[0]["texture"], "clay")


func test_profile_layers_organic() -> void:
	var layers: Array = SoilView3DScript.get_profile_layers("organic")
	assert_eq(layers.size(), 3, "Organic/loam has 3 layers")
	assert_eq(layers[0]["texture"], "loam")


func test_constants() -> void:
	assert_gt(SoilView3DScript.CUTAWAY_WIDTH, 0.0, "Cutaway width positive")
	assert_gt(SoilView3DScript.SCALE_CM, 0.0, "Scale cm positive")
