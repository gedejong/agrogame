extends CPUParticles2D
## Rain particle effect overlay. Toggle with set_raining().

var _is_raining := false


func _ready() -> void:
	emitting = false
	amount = 200
	lifetime = 1.0
	direction = Vector2(0.2, 1.0)
	spread = 10.0
	gravity = Vector2(0, 400)
	initial_velocity_min = 200.0
	initial_velocity_max = 300.0
	emission_shape = EMISSION_SHAPE_RECTANGLE
	emission_rect_extents = Vector2(640, 0)
	position = Vector2(640, -20)
	color = Color(0.6, 0.7, 0.9, 0.5)


func set_raining(raining: bool) -> void:
	_is_raining = raining
	emitting = raining


func is_raining() -> bool:
	return _is_raining
