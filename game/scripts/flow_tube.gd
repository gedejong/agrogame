class_name FlowTube
extends Node3D
## Glass-tube flow visualization: transparent outer shell + colored liquid
## fill with animated particles flowing along the tube path.
## Parameterizable: color, thickness, speed, direction, optional label.

const GLASS_SHADER := preload("res://shaders/flow_tube_glass.gdshader")
const MIN_RADIUS := 0.008
const MAX_RADIUS := 0.035
const RADIAL_SEGMENTS := 12

var _tube_mesh: MeshInstance3D = null
var _particles: GPUParticles3D = null
var _label: Label3D = null
var _material: ShaderMaterial = null


static func create(config: Dictionary) -> FlowTube:
	## Build a flow tube from config: start, end, color, magnitude, speed, label_text.
	var tube := FlowTube.new()
	var start: Vector3 = config.get("start", Vector3.ZERO)
	var end: Vector3 = config.get("end", Vector3(0, -0.1, 0))
	var color: Color = config.get("color", Color(0.376, 0.647, 0.980, 0.8))
	var magnitude: float = clampf(config.get("magnitude", 0.5), 0.01, 1.0)
	var speed: float = config.get("speed", 1.0)
	var label_text: String = config.get("label_text", "")

	tube._build_tube(start, end, color, magnitude, speed)
	if not label_text.is_empty():
		tube._build_label(start, end, label_text, color)
	tube._build_particles(start, end, color, magnitude, speed)
	return tube


func _build_tube(
	start: Vector3, end: Vector3, color: Color, magnitude: float, speed: float
) -> void:
	var dir := end - start
	var length := dir.length()
	if length < 0.001:
		return
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude)

	var cyl := CylinderMesh.new()
	cyl.height = length
	cyl.top_radius = radius
	cyl.bottom_radius = radius
	cyl.radial_segments = RADIAL_SEGMENTS

	_material = ShaderMaterial.new()
	_material.shader = GLASS_SHADER
	_material.set_shader_parameter("liquid_color", color)
	_material.set_shader_parameter("flow_speed", speed)
	_material.set_shader_parameter("fill_level", clampf(magnitude, 0.3, 0.9))
	_material.render_priority = 1

	_tube_mesh = MeshInstance3D.new()
	_tube_mesh.mesh = cyl
	_tube_mesh.material_override = _material
	_tube_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON

	# Position at midpoint, rotate to align with direction
	var mid := (start + end) * 0.5
	_tube_mesh.position = mid
	_tube_mesh.transform.basis = _basis_along(dir)
	add_child(_tube_mesh)


func _build_particles(
	start: Vector3, end: Vector3, color: Color, magnitude: float, speed: float
) -> void:
	var dir := end - start
	var length := dir.length()
	if length < 0.001:
		return

	_particles = GPUParticles3D.new()
	_particles.amount = clampi(int(magnitude * 20.0), 2, 20)
	_particles.lifetime = maxf(length / maxf(absf(speed) * 0.2, 0.01), 0.5)
	_particles.emitting = true
	_particles.visibility_aabb = AABB(Vector3(-0.1, -0.1, -0.1), Vector3(0.2, length + 0.2, 0.2))

	var mat := ParticleProcessMaterial.new()
	mat.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude) * 0.5
	mat.emission_box_extents = Vector3(radius, length * 0.45, radius)
	# No gravity — particles flow along tube via initial velocity
	mat.gravity = Vector3.ZERO
	# Particles spawn along tube length (Y-aligned) and move in Y direction
	# The tube's basis rotates Y to match start→end, so Y velocity = flow direction
	var flow_speed: float = length * speed * 0.5
	mat.initial_velocity_min = flow_speed * 0.8
	mat.initial_velocity_max = flow_speed * 1.2
	mat.direction = Vector3(0, 1, 0)
	mat.spread = 5.0
	mat.scale_min = 0.4
	mat.scale_max = 0.7
	mat.color = Color(color.r, color.g, color.b, 0.9)
	_particles.process_material = mat

	# Tiny sphere mesh for each particle
	var draw_pass := SphereMesh.new()
	draw_pass.radius = radius * 1.5
	draw_pass.height = radius * 3.0
	draw_pass.radial_segments = 4
	draw_pass.rings = 2
	var p_mat := StandardMaterial3D.new()
	p_mat.albedo_color = color
	p_mat.emission_enabled = true
	p_mat.emission = color
	p_mat.emission_energy_multiplier = 0.3
	draw_pass.material = p_mat
	_particles.draw_pass_1 = draw_pass
	_particles.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF

	var mid := (start + end) * 0.5
	_particles.position = mid
	_particles.transform.basis = _basis_along(dir)
	add_child(_particles)


func _build_label(start: Vector3, end: Vector3, text: String, color: Color) -> void:
	_label = Label3D.new()
	_label.text = text
	_label.font_size = 28
	_label.pixel_size = 0.001
	_label.modulate = Color(color.r, color.g, color.b, 0.9)
	_label.no_depth_test = true
	_label.billboard = BaseMaterial3D.BILLBOARD_DISABLED
	# Position label offset from tube, oriented along tube direction
	var mid := (start + end) * 0.5
	var tube_dir := (end - start).normalized()
	# Offset label outward from the cutaway face (+X direction)
	_label.position = mid + Vector3(0.04, 0, 0)
	# Align label along tube: look_at the end from the start
	var label_up := Vector3.UP
	if absf(tube_dir.dot(Vector3.UP)) > 0.9:
		label_up = Vector3.FORWARD
	_label.look_at(mid + tube_dir, label_up)
	_label.rotation.y += PI * 0.5
	add_child(_label)


func set_speed(speed: float) -> void:
	if _material:
		_material.set_shader_parameter("flow_speed", speed)
	if _particles and _particles.process_material:
		var mat: ParticleProcessMaterial = _particles.process_material
		var old_grav := mat.gravity
		mat.gravity = old_grav.normalized() * speed * 0.3


func set_magnitude(magnitude: float) -> void:
	magnitude = clampf(magnitude, 0.01, 1.0)
	if _material:
		_material.set_shader_parameter("fill_level", clampf(magnitude, 0.3, 0.9))
	if _tube_mesh and _tube_mesh.mesh is CylinderMesh:
		var cyl: CylinderMesh = _tube_mesh.mesh
		var r := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude)
		cyl.top_radius = r
		cyl.bottom_radius = r
	if _particles:
		_particles.amount = clampi(int(magnitude * 20.0), 2, 20)


static func _basis_along(dir: Vector3) -> Basis:
	# CylinderMesh is Y-aligned; rotate to align Y with dir
	var up := dir.normalized()
	if up.is_zero_approx():
		return Basis.IDENTITY
	# Find a perpendicular vector for the basis
	var side := Vector3.RIGHT if absf(up.dot(Vector3.RIGHT)) < 0.99 else Vector3.FORWARD
	var x_axis := up.cross(side).normalized()
	var z_axis := x_axis.cross(up).normalized()
	return Basis(x_axis, up, z_axis)
