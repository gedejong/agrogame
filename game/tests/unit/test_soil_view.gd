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


func test_nutrient_bars_defined() -> void:
	for key: String in ["NO3", "NH4", "P", "SOM", "Water", "pH", "Microbe"]:
		assert_true(SoilViewScript.NUTRIENT_BARS.has(key), "Bar config for %s" % key)


func test_nutrient_bar_has_required_fields() -> void:
	for key: String in SoilViewScript.NUTRIENT_BARS:
		var cfg: Dictionary = SoilViewScript.NUTRIENT_BARS[key]
		assert_true(cfg.has("color"), "%s has color" % key)
		assert_true(cfg.has("max"), "%s has max" % key)
		assert_true(cfg.has("opt_min"), "%s has opt_min" % key)
		assert_true(cfg.has("opt_max"), "%s has opt_max" % key)


func test_nutrient_bar_max_positive() -> void:
	for key: String in SoilViewScript.NUTRIENT_BARS:
		var cfg: Dictionary = SoilViewScript.NUTRIENT_BARS[key]
		assert_gt(cfg["max"], 0.0, "%s max > 0" % key)


func test_nutrient_bar_optimal_range_valid() -> void:
	for key: String in SoilViewScript.NUTRIENT_BARS:
		var cfg: Dictionary = SoilViewScript.NUTRIENT_BARS[key]
		assert_lte(cfg["opt_min"], cfg["opt_max"], "%s opt_min <= opt_max" % key)


func test_bar_stress_color_is_red() -> void:
	assert_gt(SoilViewScript.BAR_STRESS_COLOR.r, 0.5, "Stress color is reddish")
