extends GutTest

const FarmView3D = preload("res://scripts/farm_view_3d.gd")


func test_script_loads() -> void:
	assert_not_null(FarmView3D, "FarmView3D script loads")


func test_scene_file_exists() -> void:
	assert_true(
		FileAccess.file_exists("res://scenes/farm_view_3d.tscn"),
		"3D scene file exists",
	)
