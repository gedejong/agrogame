extends GutTest

const Rain3D = preload("res://scripts/rain_3d.gd")


func test_constants() -> void:
	assert_gt(Rain3D.MAX_AMOUNT, 0, "Max amount positive")
	assert_gt(Rain3D.FALL_HEIGHT, 0.0, "Fall height positive")


func test_rain_color() -> void:
	assert_gt(Rain3D.RAIN_COLOR.a, 0.0, "Rain has alpha > 0")
	assert_lt(Rain3D.RAIN_COLOR.a, 1.0, "Rain has alpha < 1 (translucent)")


func test_emission_box() -> void:
	assert_gt(Rain3D.EMISSION_BOX.x, 0.0, "Box width positive")
	assert_gt(Rain3D.EMISSION_BOX.z, 0.0, "Box depth positive")


func test_set_raining_on() -> void:
	var node := GPUParticles3D.new()
	node.set_script(Rain3D)
	add_child_autofree(node)
	node.set_raining(true, 5.0)
	assert_true(node.is_raining(), "Should be raining")
	assert_true(node.emitting, "Should be emitting")
	assert_eq(node.amount, 200, "5mm * 40 = 200 particles")


func test_set_raining_off() -> void:
	var node := GPUParticles3D.new()
	node.set_script(Rain3D)
	add_child_autofree(node)
	node.set_raining(true, 5.0)
	node.set_raining(false)
	assert_false(node.is_raining())
	assert_false(node.emitting)


func test_set_raining_clamps_amount() -> void:
	var node := GPUParticles3D.new()
	node.set_script(Rain3D)
	add_child_autofree(node)
	node.set_raining(true, 100.0)
	assert_lte(node.amount, Rain3D.MAX_AMOUNT, "Amount clamped to max")
	node.set_raining(true, 0.1)
	assert_gte(node.amount, 50, "Amount has minimum floor")
