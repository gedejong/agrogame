extends GutTest

const FogClouds3D = preload("res://scripts/fog_clouds_3d.gd")


func test_constants() -> void:
	assert_gt(FogClouds3D.MAX_AMOUNT, 0, "Max amount positive")


func test_cloud_color_translucent() -> void:
	assert_gt(FogClouds3D.CLOUD_COLOR.a, 0.0, "Alpha > 0")
	assert_lt(FogClouds3D.CLOUD_COLOR.a, 0.5, "Alpha low for subtle wisps")


func test_set_fog_below_threshold() -> void:
	var node := GPUParticles3D.new()
	node.set_script(FogClouds3D)
	add_child_autofree(node)
	node.set_fog_intensity(0.3)
	assert_false(node.emitting, "Below threshold = no fog wisps")


func test_set_fog_above_threshold() -> void:
	var node := GPUParticles3D.new()
	node.set_script(FogClouds3D)
	add_child_autofree(node)
	node.set_fog_intensity(0.8)
	assert_true(node.emitting, "Above threshold = fog wisps")
	assert_gt(node.amount, 0, "Nonzero particles")


func test_set_fog_at_threshold_edge() -> void:
	var node := GPUParticles3D.new()
	node.set_script(FogClouds3D)
	add_child_autofree(node)
	node.set_fog_intensity(FogClouds3D.HUMIDITY_THRESHOLD)
	assert_false(node.emitting, "Exactly at threshold = no fog")
