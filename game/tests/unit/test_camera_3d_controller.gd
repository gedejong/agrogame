extends GutTest

const Camera3DController = preload("res://scripts/camera_3d_controller.gd")


func test_zoom_constants() -> void:
	assert_eq(Camera3DController.ZOOM_MIN, 0.75, "Min ortho size is 0.75")
	assert_eq(Camera3DController.ZOOM_MAX, 60.0, "Max ortho size is 60")
	assert_lt(Camera3DController.ZOOM_MIN, Camera3DController.ZOOM_MAX, "Min below max")


func test_zoom_sensitivity() -> void:
	assert_eq(Camera3DController.ZOOM_SENSITIVITY, 0.05, "Wheel zoom sensitivity is 0.05")


func test_pan_speed() -> void:
	assert_eq(Camera3DController.PAN_SPEED, 0.05, "Pan speed is 0.05")
