extends GutTest

const Camera3DController = preload("res://scripts/camera_3d_controller.gd")


func test_zoom_constants() -> void:
	assert_eq(Camera3DController.ZOOM_MIN, 4.0, "Min zoom is 4")
	assert_eq(Camera3DController.ZOOM_MAX, 30.0, "Max zoom is 30")
	assert_eq(Camera3DController.ZOOM_STEP, 0.5, "Zoom step is 0.5")


func test_pan_speed() -> void:
	assert_eq(Camera3DController.PAN_SPEED, 0.05, "Pan speed is 0.05")
