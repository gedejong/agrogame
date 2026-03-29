extends Camera2D
## Isometric camera with pan (middle mouse drag) and zoom (scroll wheel).

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


func _zoom_in() -> void:
	var new_zoom := min(zoom.x + ZOOM_STEP, ZOOM_MAX)
	zoom = Vector2(new_zoom, new_zoom)


func _zoom_out() -> void:
	var new_zoom := max(zoom.x - ZOOM_STEP, ZOOM_MIN)
	zoom = Vector2(new_zoom, new_zoom)


func get_zoom_level() -> float:
	return zoom.x
