extends Camera3D
## Orthographic 3D camera with smooth zoom and pan.
## Controls: WASD pan, R/F zoom, mouse wheel zoom, middle-drag pan,
## trackpad pan/pinch.

const ZOOM_SENSITIVITY := 0.05
const ZOOM_MIN := 1.5
const ZOOM_MAX := 30.0
const ZOOM_SMOOTH := 8.0
const PAN_SPEED := 0.05
const KEY_PAN_SPEED := 5.0
const KEY_ZOOM_SPEED := 0.3

var _dragging := false
var _target_size: float = 10.0


func _ready() -> void:
	_target_size = size


func _process(delta: float) -> void:
	# Smooth zoom interpolation
	if not is_equal_approx(size, _target_size):
		size = lerpf(size, _target_size, minf(ZOOM_SMOOTH * delta, 1.0))
	# WASD keyboard panning — screen-aligned directions
	var rig: Node3D = get_parent()
	if not rig:
		return
	var screen_input := Vector2.ZERO
	if Input.is_key_pressed(KEY_W):
		screen_input.y -= 1.0
	if Input.is_key_pressed(KEY_S):
		screen_input.y += 1.0
	if Input.is_key_pressed(KEY_A):
		screen_input.x -= 1.0
	if Input.is_key_pressed(KEY_D):
		screen_input.x += 1.0
	if screen_input.length_squared() > 0.0:
		var world_pan := _screen_to_world(screen_input.normalized())
		rig.global_translate(world_pan * KEY_PAN_SPEED * delta * (size / 10.0))
	# R/F keyboard zoom
	if Input.is_key_pressed(KEY_R):
		_target_size = maxf(_target_size - KEY_ZOOM_SPEED * delta * size, ZOOM_MIN)
	if Input.is_key_pressed(KEY_F):
		_target_size = minf(_target_size + KEY_ZOOM_SPEED * delta * size, ZOOM_MAX)


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
	var d := event.relative * PAN_SPEED * (size / 10.0)
	var world_pan := _screen_to_world(Vector2(-d.x, -d.y))
	rig.global_translate(world_pan)


func _handle_pan_gesture(event: InputEventPanGesture) -> void:
	var rig: Node3D = get_parent()
	if not rig:
		return
	var pan_delta := event.delta * PAN_SPEED * 2.0 * (size / 10.0)
	var world_pan := _screen_to_world(Vector2(pan_delta.x, pan_delta.y))
	rig.global_translate(world_pan)


func _handle_magnify_gesture(event: InputEventMagnifyGesture) -> void:
	if event.factor > 1.0:
		_zoom_in()
	elif event.factor < 1.0:
		_zoom_out()


func _screen_to_world(screen_delta: Vector2) -> Vector3:
	## Map 2D screen-space delta to 3D world XZ movement.
	## Uses the camera's right and up vectors projected onto XZ.
	var cam_right := global_transform.basis.x
	var cam_up := global_transform.basis.y
	# Project onto XZ plane (zero out Y, normalize)
	var right_xz := Vector3(cam_right.x, 0, cam_right.z).normalized()
	var up_xz := Vector3(cam_up.x, 0, cam_up.z).normalized()
	return right_xz * screen_delta.x + up_xz * (-screen_delta.y)


func _zoom_in() -> void:
	_target_size = maxf(_target_size * (1.0 - ZOOM_SENSITIVITY), ZOOM_MIN)


func _zoom_out() -> void:
	_target_size = minf(_target_size * (1.0 + ZOOM_SENSITIVITY), ZOOM_MAX)
