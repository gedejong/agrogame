extends CPUParticles2D
## Rain particle effect overlay on CanvasLayer. Toggle with set_raining().
## Positioned in screen space — unaffected by camera pan/zoom.

var _is_raining := false


func _ready() -> void:
	emitting = false
	amount = 400
	lifetime = 1.5
	direction = Vector2(0.15, 1.0)
	spread = 5.0
	gravity = Vector2(0, 600)
	initial_velocity_min = 200.0
	initial_velocity_max = 400.0
	emission_shape = EMISSION_SHAPE_RECTANGLE
	# Wide enough to cover full viewport (1280px) from center
	emission_rect_extents = Vector2(700, 0)
	# Top-center of screen
	position = Vector2(640, -20)
	color = Color(0.5, 0.65, 0.9, 0.6)
	z_index = 100


func set_raining(raining: bool) -> void:
	_is_raining = raining
	emitting = raining


func is_raining() -> bool:
	return _is_raining
