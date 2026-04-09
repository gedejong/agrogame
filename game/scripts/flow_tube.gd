class_name FlowTube
extends Node3D
## Glass-tube flow visualization: transparent outer shell + colored liquid
## fill with animated particles flowing along the tube path.
## Parameterizable: color, thickness, speed, direction, optional label.

const MIN_RADIUS := 0.003
const MAX_RADIUS := 0.03
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
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, sqrt(magnitude))
	var mid := (start + end) * 0.5
	var tube_basis := _basis_along(dir)

	# Single mesh: colored tube with slight transparency and specular
	var cyl := CylinderMesh.new()
	cyl.height = length
	cyl.top_radius = radius
	cyl.bottom_radius = radius
	cyl.radial_segments = RADIAL_SEGMENTS
	cyl.cap_top = false
	cyl.cap_bottom = false
	# Visual mesh: transparent glass, no depth write, no shadow cast
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
	_tube_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_tube_mesh.position = mid
	_tube_mesh.transform.basis = tube_basis
	add_child(_tube_mesh)
	# Shadow-only mesh: invisible opaque duplicate for shadow casting
	var shadow_mesh := MeshInstance3D.new()
	shadow_mesh.mesh = cyl
	shadow_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
	shadow_mesh.position = mid
	shadow_mesh.transform.basis = tube_basis
	add_child(shadow_mesh)


func _build_path_tube(path: Array, color: Color, magnitude: float) -> void:
	## Build a continuous tube mesh along a path using SurfaceTool.
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, sqrt(magnitude))
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var segs := RADIAL_SEGMENTS
	# Propagate previous x_axis to avoid cross-section twists at direction changes
	var prev_x := Vector3.ZERO
	for pi in range(path.size()):
		var p: Vector3 = path[pi]
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
		# Rotation-minimizing frame: project previous x_axis onto plane perpendicular to fwd
		var x_ax := Vector3.ZERO
		if prev_x.is_zero_approx():
			var ref := Vector3.FORWARD if absf(fwd.dot(Vector3.FORWARD)) < 0.9 else Vector3.RIGHT
			x_ax = fwd.cross(ref).normalized()
		else:
			x_ax = (prev_x - fwd * prev_x.dot(fwd)).normalized()
			if x_ax.is_zero_approx():
				x_ax = prev_x
		var z_ax := fwd.cross(x_ax).normalized()
		prev_x = x_ax
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
	var committed_mesh: ArrayMesh = st.commit()
	# Visual mesh: transparent, no shadow
	var mesh_inst := MeshInstance3D.new()
	mesh_inst.mesh = committed_mesh
	mesh_inst.material_override = mat
	mesh_inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mesh_inst)
	_tube_mesh = mesh_inst
	# Shadow-only duplicate
	var shadow_inst := MeshInstance3D.new()
	shadow_inst.mesh = committed_mesh
	shadow_inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_SHADOWS_ONLY
	add_child(shadow_inst)


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
	var base_r := lerpf(MIN_RADIUS, MAX_RADIUS, sqrt(magnitude)) * 0.2
	var p_mat := StandardMaterial3D.new()
	p_mat.albedo_color = Color(1.0, 1.0, 1.0, 0.95)
	p_mat.emission_enabled = true
	p_mat.emission = color
	p_mat.emission_energy_multiplier = 1.5
	# Use truly random values via a seeded sequence (not golden ratio)
	var rng := RandomNumberGenerator.new()
	rng.seed = int(path[0].x * 1000.0 + path[0].z * 7000.0) + count
	for i in range(count):
		var size_mult: float = 0.4 + rng.randf() * 0.7
		var speed_mult: float = 0.6 + rng.randf() * 0.8
		var sphere := SphereMesh.new()
		sphere.radius = base_r * size_mult
		sphere.height = base_r * size_mult * 2.0
		sphere.radial_segments = 4
		sphere.rings = 2
		sphere.material = p_mat
		var follow := PathFollow3D.new()
		follow.loop = true
		follow.progress_ratio = rng.randf()
		follow.set_meta("flow_speed", absf(speed) * 0.8 * speed_mult)
		# Store random wobble parameters for radial animation
		follow.set_meta("wobble_phase", rng.randf() * TAU)
		follow.set_meta("wobble_radius", rng.randf() * base_r * 1.5)
		var mi := MeshInstance3D.new()
		mi.mesh = sphere
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
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
	var radius := lerpf(MIN_RADIUS, MAX_RADIUS, sqrt(magnitude)) * 0.3
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
	_label.visible = false
	add_child(_label)
	# Hover detection area along the tube
	var area := Area3D.new()
	var coll := CollisionShape3D.new()
	var shape := CylinderShape3D.new()
	var length := (end - start).length()
	shape.height = maxf(length, 0.05)
	shape.radius = 0.04
	coll.shape = shape
	area.add_child(coll)
	area.position = mid
	area.transform.basis = _basis_along(end - start)
	area.input_ray_pickable = true
	area.mouse_entered.connect(func() -> void: _label.visible = true)
	area.mouse_exited.connect(func() -> void: _label.visible = false)
	add_child(area)


func fade_in(duration: float = 0.4) -> void:
	if _material:
		var target_alpha: float = _material.albedo_color.a
		_material.albedo_color.a = 0.0
		var tw := create_tween()
		tw.tween_method(
			func(a: float) -> void: _material.albedo_color.a = a,
			0.0,
			target_alpha,
			duration,
		)


func fade_out(duration: float = 0.4) -> void:
	if _material:
		var tw := create_tween()
		tw.tween_method(
			func(a: float) -> void: _material.albedo_color.a = a,
			_material.albedo_color.a,
			0.0,
			duration,
		)
		tw.tween_callback(queue_free)
	else:
		queue_free()


func tween_magnitude(new_mag: float, duration: float = 0.4) -> void:
	new_mag = clampf(new_mag, 0.01, 1.0)
	var tw := create_tween()
	tw.set_parallel(true)
	if _tube_mesh and _tube_mesh.mesh is CylinderMesh:
		var cyl: CylinderMesh = _tube_mesh.mesh
		var target_r := lerpf(MIN_RADIUS, MAX_RADIUS, sqrt(new_mag))
		tw.tween_method(
			func(r: float) -> void:
				cyl.top_radius = r
				cyl.bottom_radius = r,
			cyl.top_radius,
			target_r,
			duration,
		)
	if _particles:
		var target_count := clampi(int(new_mag * 20.0), 2, 20)
		(
			tw
			. tween_callback(func() -> void: _particles.amount = target_count)
			. set_delay(duration * 0.5)
		)


func pulse(intensity: float = 2.0, duration: float = 0.5) -> void:
	if _material:
		var orig_energy: float = _material.emission_energy_multiplier
		_material.emission_energy_multiplier = orig_energy * intensity
		var tw := create_tween()
		tw.tween_property(_material, "emission_energy_multiplier", orig_energy, duration)
	# Boost path particle brightness briefly
	if has_meta("path_node"):
		var pn: Path3D = get_meta("path_node")
		for child in pn.get_children():
			if child is PathFollow3D and child.get_child_count() > 0:
				var mi: MeshInstance3D = child.get_child(0) as MeshInstance3D
				if mi and mi.mesh and mi.mesh.material:
					var mat: StandardMaterial3D = mi.mesh.material
					var orig_e: float = mat.emission_energy_multiplier
					mat.emission_energy_multiplier = orig_e * intensity
					var tw2 := create_tween()
					tw2.tween_property(mat, "emission_energy_multiplier", orig_e, duration)


func enable_gas_dissipation() -> void:
	## Make particles fade out and drift upward at the tube's end.
	## Used for CO2, NH3, N2O — gases escaping into atmosphere.
	if _particles and _particles.process_material is ParticleProcessMaterial:
		var pm: ParticleProcessMaterial = _particles.process_material
		# Slight upward gravity so particles drift up after leaving tube
		pm.gravity = Vector3(0, 0.15, 0)
		# Color ramp: full opacity → transparent at end of lifetime
		var grad := Gradient.new()
		grad.set_color(0, pm.color)
		grad.add_point(0.6, pm.color)
		grad.add_point(1.0, Color(pm.color.r, pm.color.g, pm.color.b, 0.0))
		var grad_tex := GradientTexture1D.new()
		grad_tex.gradient = grad
		pm.color_ramp = grad_tex
	# Also apply to path-following particles
	if has_meta("path_node"):
		set_meta("gas_dissipation", true)


func set_speed(speed: float) -> void:
	if _particles and _particles.process_material:
		var mat: ParticleProcessMaterial = _particles.process_material
		var flow_v: float = _particles.visibility_aabb.size.y * speed * 0.5
		mat.initial_velocity_min = flow_v * 0.9
		mat.initial_velocity_max = flow_v * 1.1


func set_magnitude(magnitude: float) -> void:
	magnitude = clampf(magnitude, 0.01, 1.0)
	if _tube_mesh and _tube_mesh.mesh is CylinderMesh:
		var r := lerpf(MIN_RADIUS, MAX_RADIUS, sqrt(magnitude))
		(_tube_mesh.mesh as CylinderMesh).top_radius = r
		(_tube_mesh.mesh as CylinderMesh).bottom_radius = r
	if _particles:
		_particles.amount = clampi(int(magnitude * 20.0), 2, 20)


func _process(delta: float) -> void:
	if not has_meta("path_node"):
		set_process(false)
		return
	var pn: Path3D = get_meta("path_node")
	var t: float = fmod(Time.get_ticks_msec() * 0.001, 100.0)
	var is_gas: bool = has_meta("gas_dissipation")
	for child in pn.get_children():
		if child is PathFollow3D:
			var spd: float = child.get_meta("flow_speed")
			child.progress_ratio = fmod(child.progress_ratio + spd * delta, 1.0)
			var phase: float = child.get_meta("wobble_phase")
			var wobble_r: float = child.get_meta("wobble_radius")
			var mi: MeshInstance3D = child.get_child(0) as MeshInstance3D
			mi.position.x = sin(t * 3.0 + phase) * wobble_r
			mi.position.z = cos(t * 2.3 + phase * 1.7) * wobble_r
			# Gas dissipation: fade out + upward drift near end of path
			if is_gas:
				var prog: float = child.progress_ratio
				var fade: float = 1.0 - smoothstep(0.6, 1.0, prog)
				mi.transparency = 1.0 - fade
				mi.position.y = (1.0 - fade) * 0.03


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
