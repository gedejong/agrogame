extends Camera3D
## Orthographic 3D camera with smooth zoom and pan.
## Matches isometric angle: 45° azimuth, 30° elevation.
## Zoom adjusts orthographic size; pan translates the camera rig.

const ZOOM_SENSITIVITY := 0.08
const ZOOM_MIN := 1.5
const ZOOM_MAX := 30.0
const ZOOM_SMOOTH := 8.0
const PAN_SPEED := 0.05

var _dragging := false
var _target_size: float = 10.0


func _ready() -> void:
	_target_size = size


func _process(delta: float) -> void:
	# Smooth zoom interpolation
	if not is_equal_approx(size, _target_size):
		size = lerpf(size, _target_size, minf(ZOOM_SMOOTH * delta, 1.0))


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		_handle_mouse_button(event as InputEventMouseButton)
	elif event is InputEventMouseMotion and _dragging:
		_handle_drag(event as InputEventMouseMotion)
	elif event is InputEventPanGesture:
		_handle_pan_gesture(event as InputEventPanGesture)
	elif event is InputEventMagnifyGesture:
		_handle_magnify_gesture(event as InputEventMagnifyGesture)


func _handle_mouse_button(event: InputEventMouseButton) -> void:
	if event.button_index == MOUSE_BUTTON_MIDDLE:
		_dragging = event.pressed
	elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
		_zoom_in()
	elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		_zoom_out()


func _handle_drag(event: InputEventMouseMotion) -> void:
	var rig: Node3D = get_parent()
	if not rig:
		return
	var delta := event.relative * PAN_SPEED * (size / 10.0)
	rig.translate(Vector3(-delta.x, 0, -delta.y))


func _handle_pan_gesture(event: InputEventPanGesture) -> void:
	var rig: Node3D = get_parent()
	if not rig:
		return
	var pan_delta := event.delta * PAN_SPEED * 2.0 * (size / 10.0)
	rig.translate(Vector3(pan_delta.x, 0, pan_delta.y))


func _handle_magnify_gesture(event: InputEventMagnifyGesture) -> void:
	if event.factor > 1.0:
		_zoom_in()
	elif event.factor < 1.0:
		_zoom_out()


func _zoom_in() -> void:
	# Proportional step: smaller size = finer steps
	_target_size = maxf(_target_size * (1.0 - ZOOM_SENSITIVITY), ZOOM_MIN)


func _zoom_out() -> void:
	_target_size = minf(_target_size * (1.0 + ZOOM_SENSITIVITY), ZOOM_MAX)
