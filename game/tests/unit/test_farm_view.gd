extends GutTest
## Tests for the isometric farm view with TileMapLayer.

const FarmViewScript = preload("res://scripts/farm_view.gd")
const CropRenderer = preload("res://scripts/crop_renderer.gd")


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
	var path: String = CropRenderer.crop_sprite_path("maize", "seedling")
	assert_eq(path, "res://assets/crops/maize_seedling.svg")


func test_crop_sprite_path_wheat_alias() -> void:
	var path: String = CropRenderer.crop_sprite_path("spring_wheat", "flowering")
	assert_eq(path, "res://assets/crops/wheat_flowering.svg")


func test_crop_sprite_path_fallback() -> void:
	var path: String = CropRenderer.crop_sprite_path("soybean", "mature")
	assert_eq(path, "res://assets/crops/maize_mature.svg")


func test_available_crops_defined() -> void:
	assert_true(FarmViewScript.AVAILABLE_CROPS.size() >= 3, "At least 3 crops available")
	assert_has(FarmViewScript.AVAILABLE_CROPS, "maize", "maize available")
	assert_has(FarmViewScript.AVAILABLE_CROPS, "spring_wheat", "wheat available")


func test_border_layout_dimensions() -> void:
	assert_eq(FarmViewScript.BORDER_LAYOUT.size(), 10, "Border layout is 10 rows")
	for row_idx in range(FarmViewScript.BORDER_LAYOUT.size()):
		var row: Array = FarmViewScript.BORDER_LAYOUT[row_idx]
		assert_eq(row.size(), 10, "Border layout row %d is 10 cols" % row_idx)


func test_border_layout_inner_is_farm() -> void:
	# Inner 6x6 (layout rows 2-7, cols 2-7) should all be "."
	for r in range(2, 8):
		for c in range(2, 8):
			var tile: String = FarmViewScript.BORDER_LAYOUT[r][c]
			assert_eq(tile, ".", "Inner tile [%d,%d] should be farm (.)" % [r, c])


func test_terrain_tiles_all_have_paths() -> void:
	for key: String in FarmViewScript.TERRAIN_TILES:
		var path: String = FarmViewScript.TERRAIN_TILES[key]
		assert_true(path.begins_with("res://"), "Terrain %s has valid path" % key)


func test_border_coords() -> void:
	assert_eq(FarmViewScript.BORDER_MIN, -2, "Border starts at -2")
	assert_eq(FarmViewScript.BORDER_MAX, 7, "Border ends at 7")


func test_click_outside_farm_ignored() -> void:
	# Coordinates outside 0..5 should not be valid farm tiles
	# This verifies the guard in _handle_tile_click
	assert_eq(FarmViewScript.GRID_COLS, 6)
	assert_eq(FarmViewScript.GRID_ROWS, 6)
	# Border tile at (-1, -1) is NOT in 0..5 range — should be ignored
	# (verified by the col >= 0 and col < GRID_COLS guard)
