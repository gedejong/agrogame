extends CPUParticles2D
## Rain particle effect overlay on CanvasLayer. Toggle with set_raining().

var _is_raining := false


func _ready() -> void:
	emitting = false
	amount = 300
	lifetime = 1.2
	direction = Vector2(0.2, 1.0)
	spread = 10.0
	gravity = Vector2(0, 500)
	initial_velocity_min = 250.0
	initial_velocity_max = 350.0
	emission_shape = EMISSION_SHAPE_RECTANGLE
	emission_rect_extents = Vector2(640, 0)
	# Centered at top of viewport (CanvasLayer = screen coords)
	position = Vector2(640, -10)
	color = Color(0.6, 0.75, 0.95, 0.4)


func set_raining(raining: bool) -> void:
	_is_raining = raining
	emitting = raining


func is_raining() -> bool:
	return _is_raining
