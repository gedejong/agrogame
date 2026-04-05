extends GutTest

const FarmView = preload("res://scripts/farm_view.gd")


func test_script_loads() -> void:
	assert_not_null(FarmView, "FarmView script loads")


func test_scene_file_exists() -> void:
	assert_true(
		FileAccess.file_exists("res://scenes/farm_view.tscn"),
		"3D scene file exists",
	)


func test_grid_dimensions() -> void:
	assert_eq(FarmView.GRID_COLS, 6, "6 columns")
	assert_eq(FarmView.GRID_ROWS, 6, "6 rows")


func test_soil_type_for_columns() -> void:
	assert_eq(FarmView._soil_type_for(0), "sandy")
	assert_eq(FarmView._soil_type_for(1), "sandy")
	assert_eq(FarmView._soil_type_for(2), "organic")
	assert_eq(FarmView._soil_type_for(3), "organic")
	assert_eq(FarmView._soil_type_for(4), "clay")
	assert_eq(FarmView._soil_type_for(5), "clay")


func test_available_crops() -> void:
	assert_true(FarmView.AVAILABLE_CROPS.size() >= 3)
	assert_has(FarmView.AVAILABLE_CROPS, "maize")
	assert_has(FarmView.AVAILABLE_CROPS, "spring_wheat")
