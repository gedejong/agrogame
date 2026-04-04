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
