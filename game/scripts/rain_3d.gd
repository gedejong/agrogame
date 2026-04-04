extends GPUParticles3D
## 3D rain particle system — replaces CPUParticles2D for 3D mode.
## Rain falls in world space over the farm grid.
## Intensity scales with daily precipitation from the API.

const RAIN_COLOR := Color(0.55, 0.65, 0.85, 0.5)
const MAX_AMOUNT := 800
const EMISSION_BOX := Vector3(4.0, 0.1, 4.0)
const FALL_HEIGHT := 6.0

var _is_raining := false


func _ready() -> void:
	emitting = false
	amount = MAX_AMOUNT
	lifetime = 0.6
	visibility_aabb = AABB(Vector3(-5, -2, -5), Vector3(10, 10, 10))
	position = Vector3(0, FALL_HEIGHT, 0)
	var mat := ParticleProcessMaterial.new()
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	mat.emission_box_extents = EMISSION_BOX
	mat.gravity = Vector3(0, -18, 0)
	mat.initial_velocity_min = 2.0
	mat.initial_velocity_max = 4.0
	mat.direction = Vector3(0.05, -1, 0.05)
	mat.spread = 3.0
	mat.color = RAIN_COLOR
	mat.scale_min = 0.3
	mat.scale_max = 0.6
	process_material = mat
	# Thin stretched quad for each raindrop
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.01, 0.08)
	draw_pass_1 = mesh
	var draw_mat := StandardMaterial3D.new()
	draw_mat.albedo_color = RAIN_COLOR
	draw_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	draw_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	draw_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material_override = draw_mat


func set_raining(raining: bool, intensity_mm: float = 5.0) -> void:
	_is_raining = raining
	if raining:
		amount = clampi(int(intensity_mm * 80.0), 50, MAX_AMOUNT)
		emitting = true
	else:
		emitting = false


func is_raining() -> bool:
	return _is_raining
