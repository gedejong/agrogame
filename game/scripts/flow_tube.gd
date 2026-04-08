class_name FlowTube
extends Node3D
## Glass-tube flow visualization: transparent outer shell + colored liquid
## fill with animated particles flowing along the tube path.
## Parameterizable: color, thickness, speed, direction, optional label.

const MIN_RADIUS := 0.008
const MAX_RADIUS := 0.035
const RADIAL_SEGMENTS := 12

var _tube_mesh: MeshInstance3D = null
var _particles: GPUParticles3D = null
var _label: Label3D = null
var _material: StandardMaterial3D = null


static func create(config: Dictionary) -> FlowTube:
	## Build a flow tube from config: start, end, color, magnitude, speed, label_text.
	var tube := FlowTube.new()
	var start: Vector3 = config.get("start", Vector3.ZERO)
	var end: Vector3 = config.get("end", Vector3(0, -0.1, 0))
	var color: Color = config.get("color", Color(0.376, 0.647, 0.980, 0.8))
	var magnitude: float = clampf(config.get("magnitude", 0.5), 0.01, 1.0)
	var speed: float = config.get("speed", 1.0)
	var label_text: String = config.get("label_text", "")

	tube._build_tube(start, end, color, magnitude)
	if not label_text.is_empty():
		tube._build_label(start, end, label_text, color)
	tube._build_particles(start, end, color, magnitude, speed)
	return tube


func _build_tube(start: Vector3, end: Vector3, color: Color, magnitude: float) -> void:
	var dir := end - start
	var length := dir.length()
	if length < 0.001:
		return
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude)
	var mid := (start + end) * 0.5
	var basis := _basis_along(dir)

	# Single mesh: colored tube with slight transparency and specular
	var cyl := CylinderMesh.new()
	cyl.height = length
	cyl.top_radius = radius
	cyl.bottom_radius = radius
	cyl.radial_segments = RADIAL_SEGMENTS
	cyl.cap_top = false
	cyl.cap_bottom = false
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(color.r, color.g, color.b, 0.55)
	mat.metallic = 0.15
	mat.metallic_specular = 0.6
	mat.roughness = 0.15
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 0.1
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_material = mat
	_tube_mesh = MeshInstance3D.new()
	_tube_mesh.mesh = cyl
	_tube_mesh.material_override = mat
	_tube_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	_tube_mesh.position = mid
	_tube_mesh.transform.basis = basis
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
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude) * 0.3
	# Tight emission: particles spawn within tube radius, along tube length
	mat.emission_box_extents = Vector3(radius, length * 0.4, radius)
	mat.gravity = Vector3.ZERO
	# Flow along tube axis (Y in local space, rotated by tube basis)
	var flow_speed: float = length * speed * 0.5
	mat.initial_velocity_min = flow_speed * 0.9
	mat.initial_velocity_max = flow_speed * 1.1
	mat.direction = Vector3(0, 1, 0)
	mat.spread = 1.0
	mat.scale_min = 0.3
	mat.scale_max = 0.5
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
	_label.outline_size = 6
	_label.outline_modulate = Color(0, 0, 0, 0.6)
	_label.modulate = Color(color.r, color.g, color.b, 1.0)
	_label.no_depth_test = true
	_label.render_priority = 10
	_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	var mid := (start + end) * 0.5
	_label.position = mid + Vector3(0.05, 0.02, 0)
	add_child(_label)


func set_speed(speed: float) -> void:
	if _particles and _particles.process_material:
		var mat: ParticleProcessMaterial = _particles.process_material
		var flow_v: float = _particles.visibility_aabb.size.y * speed * 0.5
		mat.initial_velocity_min = flow_v * 0.9
		mat.initial_velocity_max = flow_v * 1.1


func set_magnitude(magnitude: float) -> void:
	magnitude = clampf(magnitude, 0.01, 1.0)
	if _tube_mesh and _tube_mesh.mesh is CylinderMesh:
		var r := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude)
		(_tube_mesh.mesh as CylinderMesh).top_radius = r
		(_tube_mesh.mesh as CylinderMesh).bottom_radius = r
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
