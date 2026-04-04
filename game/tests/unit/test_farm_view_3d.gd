extends GutTest

const FarmView3D = preload("res://scripts/farm_view_3d.gd")


func test_script_loads() -> void:
	assert_not_null(FarmView3D, "FarmView3D script loads")


func test_scene_file_exists() -> void:
	assert_true(
		FileAccess.file_exists("res://scenes/farm_view_3d.tscn"),
		"3D scene file exists",
	)


func test_grid_dimensions() -> void:
	assert_eq(FarmView3D.GRID_COLS, 6, "6 columns")
	assert_eq(FarmView3D.GRID_ROWS, 6, "6 rows")


func test_soil_type_for_columns() -> void:
	assert_eq(FarmView3D._soil_type_for(0), "sandy")
	assert_eq(FarmView3D._soil_type_for(1), "sandy")
	assert_eq(FarmView3D._soil_type_for(2), "organic")
	assert_eq(FarmView3D._soil_type_for(3), "organic")
	assert_eq(FarmView3D._soil_type_for(4), "clay")
	assert_eq(FarmView3D._soil_type_for(5), "clay")


func test_available_crops() -> void:
	assert_true(FarmView3D.AVAILABLE_CROPS.size() >= 3)
	assert_has(FarmView3D.AVAILABLE_CROPS, "maize")
	assert_has(FarmView3D.AVAILABLE_CROPS, "spring_wheat")
