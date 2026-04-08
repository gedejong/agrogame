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
	## Optional "path": Array[Vector3] for multi-segment tubes with curves.
	var tube := FlowTube.new()
	var start: Vector3 = config.get("start", Vector3.ZERO)
	var end: Vector3 = config.get("end", Vector3(0, -0.1, 0))
	var color: Color = config.get("color", Color(0.376, 0.647, 0.980, 0.8))
	var magnitude: float = clampf(config.get("magnitude", 0.5), 0.01, 1.0)
	var speed: float = config.get("speed", 1.0)
	var label_text: String = config.get("label_text", "")
	var path: Array = config.get("path", [])

	if path.size() >= 2:
		tube._build_path_tube(path, color, magnitude)
		tube._build_path_particles(path, color, magnitude, speed)
		if not label_text.is_empty():
			tube._build_label(path[0], path[path.size() - 1], label_text, color)
	else:
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
	mat.albedo_color = Color(color.r, color.g, color.b, 0.25)
	mat.metallic = 0.2
	mat.metallic_specular = 0.7
	mat.roughness = 0.08
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 0.08
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_material = mat
	_tube_mesh = MeshInstance3D.new()
	_tube_mesh.mesh = cyl
	_tube_mesh.material_override = mat
	_tube_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	_tube_mesh.position = mid
	_tube_mesh.transform.basis = basis
	add_child(_tube_mesh)


func _build_path_tube(path: Array, color: Color, magnitude: float) -> void:
	## Build a continuous tube mesh along a path using SurfaceTool.
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude)
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var segs := RADIAL_SEGMENTS
	# Consistent reference up vector for stable cross-sections
	var ref_up := Vector3.UP
	# Generate rings of vertices at each path point
	for pi in range(path.size()):
		var p: Vector3 = path[pi]
		# Smooth direction: average of forward and backward differences
		var fwd := Vector3.FORWARD
		if pi < path.size() - 1 and pi > 0:
			var f1 := (Vector3(path[pi + 1]) - p).normalized()
			var f2 := (p - Vector3(path[pi - 1])).normalized()
			fwd = ((f1 + f2) * 0.5).normalized()
		elif pi < path.size() - 1:
			fwd = (Vector3(path[pi + 1]) - p).normalized()
		elif pi > 0:
			fwd = (p - Vector3(path[pi - 1])).normalized()
		if fwd.is_zero_approx():
			fwd = Vector3.FORWARD
		# Stable basis using consistent up reference
		var x_ax := ref_up.cross(fwd).normalized()
		if x_ax.is_zero_approx():
			x_ax = Vector3.RIGHT
		var z_ax := fwd.cross(x_ax).normalized()
		var v: float = float(pi) / float(maxi(path.size() - 1, 1))
		for si in range(segs):
			var angle: float = float(si) / float(segs) * TAU
			var ring_offset := (x_ax * cos(angle) + z_ax * sin(angle)) * radius
			st.set_normal((x_ax * cos(angle) + z_ax * sin(angle)).normalized())
			st.set_uv(Vector2(float(si) / float(segs), v))
			st.add_vertex(p + ring_offset)
	# Connect rings with triangles
	for pi in range(path.size() - 1):
		var base_a: int = pi * segs
		var base_b: int = (pi + 1) * segs
		for si in range(segs):
			var s_next: int = (si + 1) % segs
			st.add_index(base_a + si)
			st.add_index(base_b + si)
			st.add_index(base_b + s_next)
			st.add_index(base_a + si)
			st.add_index(base_b + s_next)
			st.add_index(base_a + s_next)
	var mat := StandardMaterial3D.new()
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.albedo_color = Color(color.r, color.g, color.b, 0.25)
	mat.metallic = 0.2
	mat.metallic_specular = 0.7
	mat.roughness = 0.08
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 0.08
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	_material = mat
	var mesh_inst := MeshInstance3D.new()
	mesh_inst.mesh = st.commit()
	mesh_inst.material_override = mat
	mesh_inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	add_child(mesh_inst)
	_tube_mesh = mesh_inst


func _build_path_particles(path: Array, color: Color, magnitude: float, speed: float) -> void:
	if path.size() < 2:
		return
	var path_node := Path3D.new()
	var curve := Curve3D.new()
	# Add points with smooth tangent handles to prevent jitter at joints
	for pi in range(path.size()):
		var pt: Vector3 = path[pi]
		var tangent := Vector3.ZERO
		if pi < path.size() - 1 and pi > 0:
			tangent = (Vector3(path[pi + 1]) - Vector3(path[pi - 1])) * 0.25
		elif pi < path.size() - 1:
			tangent = (Vector3(path[pi + 1]) - pt) * 0.25
		elif pi > 0:
			tangent = (pt - Vector3(path[pi - 1])) * 0.25
		curve.add_point(pt, -tangent, tangent)
	path_node.curve = curve
	add_child(path_node)
	var count: int = clampi(int(magnitude * 15.0), 4, 20)
	var base_r := lerpf(MIN_RADIUS, MAX_RADIUS, magnitude) * 0.2
	var p_mat := StandardMaterial3D.new()
	p_mat.albedo_color = Color(1.0, 1.0, 1.0, 0.95)
	p_mat.emission_enabled = true
	p_mat.emission = color
	p_mat.emission_energy_multiplier = 1.5
	for i in range(count):
		var hash_v: float = fmod(float(i * 7 + 3) * 0.618, 1.0)
		var size_mult: float = 0.5 + hash_v * 0.6
		var speed_mult: float = 0.7 + fmod(float(i * 13 + 5) * 0.618, 1.0) * 0.6
		var sphere := SphereMesh.new()
		sphere.radius = base_r * size_mult
		sphere.height = base_r * size_mult * 2.0
		sphere.radial_segments = 4
		sphere.rings = 2
		sphere.material = p_mat
		var follow := PathFollow3D.new()
		follow.loop = true
		# Random start position along path (not all at 0)
		follow.progress_ratio = fmod(float(i) / float(count) + hash_v * 0.3, 1.0)
		follow.set_meta("flow_speed", absf(speed) * 0.8 * speed_mult)
		var mi := MeshInstance3D.new()
		mi.mesh = sphere
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		var off_x: float = (hash_v - 0.5) * base_r * 1.2
		var off_z: float = (fmod(float(i * 11) * 0.618, 1.0) - 0.5) * base_r * 1.2
		mi.position = Vector3(off_x, 0, off_z)
		follow.add_child(mi)
		path_node.add_child(follow)
	# Store for _process animation
	set_meta("path_node", path_node)
	set_process(true)


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
	p_mat.albedo_color = Color(1.0, 1.0, 1.0, 0.95)
	p_mat.emission_enabled = true
	p_mat.emission = color
	p_mat.emission_energy_multiplier = 1.2
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


func _process(delta: float) -> void:
	if not has_meta("path_node"):
		set_process(false)
		return
	var pn: Path3D = get_meta("path_node")
	for child in pn.get_children():
		if child is PathFollow3D:
			var spd: float = child.get_meta("flow_speed")
			child.progress_ratio = fmod(child.progress_ratio + spd * delta, 1.0)


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
