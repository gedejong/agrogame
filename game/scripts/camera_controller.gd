extends Camera2D
## Isometric camera with pan and zoom.
## Supports mouse (middle-drag, scroll wheel) and trackpad (two-finger
## pan gesture, pinch-to-zoom).

const ZOOM_STEP := 0.1
const ZOOM_MIN := 0.5
const ZOOM_MAX := 3.0
const PAN_SPEED := 1.0

var _dragging := false
var _drag_start := Vector2.ZERO


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
		_drag_start = event.position
	elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
		_zoom_in()
	elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		_zoom_out()


func _handle_drag(event: InputEventMouseMotion) -> void:
	var delta := event.relative * PAN_SPEED / zoom
	position -= delta


func _handle_pan_gesture(event: InputEventPanGesture) -> void:
	## Two-finger trackpad scroll → camera pan
	var pan_delta := event.delta * 10.0 / zoom
	position += pan_delta


func _handle_magnify_gesture(event: InputEventMagnifyGesture) -> void:
	## Trackpad pinch-to-zoom
	if event.factor > 1.0:
		_zoom_in()
	elif event.factor < 1.0:
		_zoom_out()


func _zoom_in() -> void:
	var new_zoom: float = min(zoom.x + ZOOM_STEP, ZOOM_MAX)
	zoom = Vector2(new_zoom, new_zoom)


func _zoom_out() -> void:
	var new_zoom: float = max(zoom.x - ZOOM_STEP, ZOOM_MIN)
	zoom = Vector2(new_zoom, new_zoom)


func get_zoom_level() -> float:
	return zoom.x
