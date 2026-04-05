extends GPUParticles3D
## Animated fog wisps drifting across the farm.
## Enabled when humidity is high (rain + low temp spread).

const MAX_AMOUNT := 20
const CLOUD_COLOR := Color(0.85, 0.88, 0.92, 0.15)


func _ready() -> void:
	emitting = false
	amount = MAX_AMOUNT
	lifetime = 8.0
	visibility_aabb = AABB(Vector3(-8, -1, -8), Vector3(16, 4, 16))
	position = Vector3(0, 0.3, 0)
	var mat := ParticleProcessMaterial.new()
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	mat.emission_box_extents = Vector3(5.0, 0.2, 5.0)
	mat.gravity = Vector3(0, 0, 0)
	mat.initial_velocity_min = 0.3
	mat.initial_velocity_max = 0.6
	mat.direction = Vector3(1.0, 0.05, 0.3)
	mat.spread = 15.0
	mat.scale_min = 2.0
	mat.scale_max = 4.0
	mat.color = CLOUD_COLOR
	process_material = mat
	var mesh := QuadMesh.new()
	mesh.size = Vector2(1.0, 0.4)
	draw_pass_1 = mesh
	var draw_mat := StandardMaterial3D.new()
	draw_mat.albedo_color = CLOUD_COLOR
	draw_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	draw_mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	draw_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material_override = draw_mat


func set_fog_intensity(humidity: float) -> void:
	## humidity in [0, 1]. Above 0.2 = fog wisps appear.
	if humidity > 0.2:
		amount = clampi(int(humidity * float(MAX_AMOUNT)), 3, MAX_AMOUNT)
		emitting = true
	else:
		emitting = false
