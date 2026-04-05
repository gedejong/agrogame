extends GPUParticles3D
## Animated fog wisps drifting across the farm.
## Only appear at high humidity (near-fog conditions).

const MAX_AMOUNT := 15
const CLOUD_COLOR := Color(0.85, 0.88, 0.92, 0.12)
const HUMIDITY_THRESHOLD := 0.6


func _ready() -> void:
	emitting = false
	amount = MAX_AMOUNT
	lifetime = 10.0
	visibility_aabb = AABB(Vector3(-8, -1, -8), Vector3(16, 4, 16))
	position = Vector3(0, 0.3, 0)
	var mat := ParticleProcessMaterial.new()
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	mat.emission_box_extents = Vector3(6.0, 0.3, 6.0)
	mat.gravity = Vector3(0, 0, 0)
	mat.initial_velocity_min = 0.2
	mat.initial_velocity_max = 0.5
	mat.direction = Vector3(1.0, 0.02, 0.3)
	mat.spread = 20.0
	mat.scale_min = 2.0
	mat.scale_max = 5.0
	mat.color = CLOUD_COLOR
	process_material = mat
	# Soft circular fog puff texture
	var mesh := QuadMesh.new()
	mesh.size = Vector2(1.0, 0.5)
	draw_pass_1 = mesh
	var draw_mat := StandardMaterial3D.new()
	draw_mat.albedo_color = CLOUD_COLOR
	draw_mat.albedo_texture = _generate_soft_circle()
	draw_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	draw_mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	draw_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material_override = draw_mat


func set_fog_intensity(humidity: float) -> void:
	## humidity in [0, 1]. Only fog-like conditions (>0.6) produce wisps.
	if humidity > HUMIDITY_THRESHOLD:
		var intensity: float = (humidity - HUMIDITY_THRESHOLD) / (1.0 - HUMIDITY_THRESHOLD)
		amount = clampi(int(intensity * float(MAX_AMOUNT)), 2, MAX_AMOUNT)
		emitting = true
	else:
		emitting = false


static func _generate_soft_circle() -> ImageTexture:
	## Radial gradient: white center fading to transparent edges.
	var size: int = 64
	var img := Image.create(size, size, false, Image.FORMAT_RGBA8)
	var center := float(size) / 2.0
	for y in range(size):
		for x in range(size):
			var dx: float = float(x) - center
			var dy: float = float(y) - center
			var dist: float = sqrt(dx * dx + dy * dy) / center
			var alpha: float = clampf(1.0 - dist * dist, 0.0, 1.0)
			img.set_pixel(x, y, Color(1, 1, 1, alpha * 0.5))
	return ImageTexture.create_from_image(img)
