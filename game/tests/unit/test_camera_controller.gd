extends GutTest
## Tests for isometric camera controller.

const CameraScript = preload("res://scripts/camera_controller.gd")


func test_zoom_limits() -> void:
	assert_eq(CameraScript.ZOOM_MIN, 0.5, "Min zoom = 0.5")
	assert_eq(CameraScript.ZOOM_MAX, 3.0, "Max zoom = 3.0")


func test_zoom_step() -> void:
	assert_eq(CameraScript.ZOOM_STEP, 0.1, "Zoom step = 0.1")


func test_instantiation() -> void:
	var cam = CameraScript.new()
	assert_not_null(cam, "Camera should instantiate")
	cam.free()
