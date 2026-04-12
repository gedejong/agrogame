extends GPUParticles3D
## 3D rain particle system — replaces CPUParticles2D for 3D mode.
## Rain falls in world space over the farm grid.
## Intensity scales with daily precipitation from the API.
## Gusts modulate direction and intensity over time.

const RAIN_COLOR := Color(0.55, 0.65, 0.85, 0.5)
const MAX_AMOUNT := 800
const EMISSION_BOX := Vector3(4.0, 0.1, 4.0)
const FALL_HEIGHT := 6.0
const GUST_PERIOD := 3.0
const GUST_STRENGTH := 0.3

var _is_raining := false
var _base_amount: int = 0
var _time := 0.0
var _wind_ms: float = 2.0
var _wind_dir: Vector2 = Vector2(0.7, 0.7)


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
	var mesh := QuadMesh.new()
	mesh.size = Vector2(0.01, 0.08)
	draw_pass_1 = mesh
	var draw_mat := StandardMaterial3D.new()
	draw_mat.albedo_color = RAIN_COLOR
	draw_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	draw_mat.billboard_mode = BaseMaterial3D.BILLBOARD_PARTICLES
	draw_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	material_override = draw_mat


func _process(delta: float) -> void:
	if not _is_raining:
		return
	_time += delta
	var gust: float = sin(_time * TAU / GUST_PERIOD)
	var gust2: float = sin(_time * TAU / (GUST_PERIOD * 1.7) + 1.0)
	var mat: ParticleProcessMaterial = process_material as ParticleProcessMaterial
	if not mat:
		return
	# Rain angle driven by wind speed + gust oscillation.
	# Stronger wind → more angled rain (x_component = wind_m_s * 0.1).
	var wind_factor: float = _wind_ms * 0.1
	var gust_factor: float = GUST_STRENGTH * clampf(_wind_ms / 5.0, 0.5, 2.0)
	var wind_x: float = _wind_dir.x * wind_factor + gust * gust_factor
	var wind_z: float = _wind_dir.y * wind_factor + gust2 * gust_factor * 0.6
	mat.direction = Vector3(wind_x, -1, wind_z)
	mat.spread = 3.0 + absf(gust) * 5.0


func set_raining(raining: bool, intensity_mm: float = 5.0) -> void:
	_is_raining = raining
	if raining:
		# 40 particles per mm: light drizzle (2mm)=80, moderate (5mm)=200, heavy (10mm)=400
		_base_amount = clampi(int(intensity_mm * 40.0), 50, MAX_AMOUNT)
		amount = _base_amount
		emitting = true
	else:
		emitting = false


func set_wind(wind_ms: float, wind_dir: Vector2) -> void:
	_wind_ms = wind_ms
	_wind_dir = wind_dir


func is_raining() -> bool:
	return _is_raining
