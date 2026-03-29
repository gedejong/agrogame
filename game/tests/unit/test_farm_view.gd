extends GutTest
## Tests for the isometric farm view.

const FarmViewScript = preload("res://scripts/farm_view.gd")


func test_grid_dimensions() -> void:
	assert_eq(FarmViewScript.GRID_COLS, 6, "Grid should be 6 columns")
	assert_eq(FarmViewScript.GRID_ROWS, 4, "Grid should be 4 rows")


func test_tile_dimensions() -> void:
	assert_eq(FarmViewScript.TILE_WIDTH, 64, "Isometric tile width = 64")
	assert_eq(FarmViewScript.TILE_HEIGHT, 32, "Isometric tile height = 32 (2:1)")


func test_soil_colors_defined() -> void:
	assert_true(
		FarmViewScript.SOIL_COLORS.has("sandy"),
		"Sandy soil color defined",
	)
	assert_true(
		FarmViewScript.SOIL_COLORS.has("loam"),
		"Loam soil color defined",
	)
	assert_true(
		FarmViewScript.SOIL_COLORS.has("clay"),
		"Clay soil color defined",
	)


func test_crop_stage_enum() -> void:
	assert_eq(FarmViewScript.CropStage.NONE, 0, "NONE = 0")
	assert_eq(FarmViewScript.CropStage.MATURE, 4, "MATURE = 4")
