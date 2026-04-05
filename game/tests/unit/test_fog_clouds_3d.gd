extends GutTest

const FogClouds3D = preload("res://scripts/fog_clouds_3d.gd")


func test_constants() -> void:
	assert_gt(FogClouds3D.MAX_AMOUNT, 0, "Max amount positive")


func test_cloud_color_translucent() -> void:
	assert_gt(FogClouds3D.CLOUD_COLOR.a, 0.0, "Alpha > 0")
	assert_lt(FogClouds3D.CLOUD_COLOR.a, 0.5, "Alpha low for subtle wisps")
