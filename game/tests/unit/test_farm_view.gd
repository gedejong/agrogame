extends GutTest
## Tests for the isometric farm view with TileMapLayer.

const FarmViewScript = preload("res://scripts/farm_view.gd")


func test_grid_dimensions() -> void:
	assert_eq(FarmViewScript.GRID_COLS, 6, "Grid should be 6 columns")
	assert_eq(FarmViewScript.GRID_ROWS, 6, "Grid should be 6 rows")


func test_tile_dimensions() -> void:
	assert_eq(FarmViewScript.TILE_WIDTH, 64, "Isometric tile width = 64")
	assert_eq(FarmViewScript.TILE_HEIGHT, 32, "Isometric tile height = 32 (2:1)")


func test_soil_types_defined() -> void:
	assert_eq(FarmViewScript.SOIL_TYPES.size(), 3, "3 soil types")
	assert_has(FarmViewScript.SOIL_TYPES, "sandy", "sandy in soil types")
	assert_has(FarmViewScript.SOIL_TYPES, "organic", "organic in soil types")
	assert_has(FarmViewScript.SOIL_TYPES, "clay", "clay in soil types")


func test_tile_textures_match_soil_types() -> void:
	for soil_type: String in FarmViewScript.SOIL_TYPES:
		assert_true(
			FarmViewScript.TILE_TEXTURES.has(soil_type),
			"Texture defined for %s" % soil_type,
		)


func test_crop_stage_enum() -> void:
	assert_eq(FarmViewScript.CropStage.NONE, 0, "NONE = 0")
	assert_eq(FarmViewScript.CropStage.MATURE, 4, "MATURE = 4")


func test_stress_state_enum() -> void:
	assert_eq(FarmViewScript.StressState.NONE, 0, "NONE = 0")
	assert_eq(FarmViewScript.StressState.WILTING, 1, "WILTING = 1")
	assert_eq(FarmViewScript.StressState.N_DEFICIENT, 2, "N_DEFICIENT = 2")


func test_crop_sprite_path_maize() -> void:
	var path: String = FarmViewScript._crop_sprite_path("maize", "seedling")
	assert_eq(path, "res://assets/crops/maize_seedling.svg")


func test_crop_sprite_path_wheat_alias() -> void:
	var path: String = FarmViewScript._crop_sprite_path("spring_wheat", "flowering")
	assert_eq(path, "res://assets/crops/wheat_flowering.svg")


func test_crop_sprite_path_fallback() -> void:
	var path: String = FarmViewScript._crop_sprite_path("soybean", "mature")
	# soybean has no sprites — should fall back to maize
	assert_eq(path, "res://assets/crops/maize_mature.svg")
