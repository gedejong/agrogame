extends Node3D
## 3D soil cross-section — replaces 2D soil_view.gd for 3D mode.
## Renders soil layers as open-front box meshes, water as transparent
## planes, roots as tube meshes, and nutrient info as Label3D billboards.

signal closed

const LAYER_COLORS := {
	"sand": Color(0.85, 0.78, 0.62),
	"loam": Color(0.55, 0.45, 0.35),
	"clay": Color(0.6, 0.5, 0.45),
}

const LAYER_TEXTURES := {
	"sand":
	{
		"albedo": "res://assets/textures/soil_sandy_albedo.png",
		"normal": "res://assets/textures/soil_sandy_normal.png",
	},
	"loam":
	{
		"albedo": "res://assets/textures/soil_loam_albedo.png",
		"normal": "res://assets/textures/soil_loam_normal.png",
	},
	"clay":
	{
		"albedo": "res://assets/textures/soil_clay_albedo.png",
		"normal": "res://assets/textures/soil_clay_normal.png",
	},
}

const WATER_COLOR := Color(0.3, 0.55, 0.9, 0.45)
const ROOT_COLOR := Color(0.75, 0.6, 0.4)
const CUTAWAY_WIDTH := 1.0
const CUTAWAY_DEPTH := 1.0
const SCALE_CM := 0.01

var _active := false


static func get_profile_layers(soil_type: String) -> Array:
	match soil_type:
		"sandy":
			return [
				{"depth_cm": 25, "texture": "sand", "saturation": 0.38},
				{"depth_cm": 35, "texture": "sand", "saturation": 0.37},
				{"depth_cm": 40, "texture": "sand", "saturation": 0.36},
			]
		"clay":
			return [
				{"depth_cm": 30, "texture": "clay", "saturation": 0.55},
				{"depth_cm": 35, "texture": "clay", "saturation": 0.54},
				{"depth_cm": 40, "texture": "clay", "saturation": 0.53},
			]
		_:
			return [
				{"depth_cm": 25, "texture": "loam", "saturation": 0.45},
				{"depth_cm": 35, "texture": "loam", "saturation": 0.44},
				{"depth_cm": 40, "texture": "loam", "saturation": 0.42},
			]


func show_cutaway(columns: Array[Dictionary]) -> void:
	## Each column: {pos: Vector3, soil_state: Dict, profile: Array,
	##   root_depth_cm: float, show_info: bool}
	_clear()
	position = Vector3.ZERO
	for col_data: Dictionary in columns:
		var pos: Vector3 = col_data.get("pos", Vector3.ZERO)
		var soil_state: Dictionary = col_data.get("soil_state", {})
		var profile: Array = col_data.get("profile", [])
		var rdcm: float = col_data.get("root_depth_cm", 0.0)
		var show_info: bool = col_data.get("show_info", false)
		_build_column(pos, soil_state, profile, rdcm, show_info)
	visible = true
	_active = true


func _build_column(
	pos: Vector3,
	soil_state: Dictionary,
	profile_layers: Array,
	root_depth_cm: float,
	show_info: bool,
) -> void:
	var container := Node3D.new()
	# Offset slightly below tile surface to avoid z-fighting
	container.position = Vector3(pos.x, pos.y - 0.005, pos.z)
	_build_layers(container, profile_layers, soil_state)
	if root_depth_cm > 0.0:
		_build_roots(container, profile_layers, root_depth_cm)
	if show_info:
		_build_info_labels(container, profile_layers, soil_state)
	add_child(container)


func hide_view() -> void:
	visible = false
	_active = false
	closed.emit()


func is_active() -> bool:
	return _active


func _clear() -> void:
	for child in get_children():
		child.queue_free()


func _build_layers(container: Node3D, profile_layers: Array, soil_state: Dictionary) -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	var y_offset := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 30.0)
		var tex_name: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.4)
		var h: float = depth_cm * SCALE_CM
		var base_color: Color = LAYER_COLORS.get(tex_name, LAYER_COLORS["loam"])
		# Depth darkening: lower layers get progressively darker
		var darken: float = float(i) * 0.12
		var color := base_color.darkened(darken)
		# Moisture tint: lerp toward blue based on water fill fraction
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill_frac: float = clampf(theta / maxf(sat, 0.01), 0.0, 1.0)
		color = color.lerp(WATER_COLOR, fill_frac * 0.5)
		var mesh := BoxMesh.new()
		mesh.size = Vector3(CUTAWAY_WIDTH, h, CUTAWAY_DEPTH)
		var mat := StandardMaterial3D.new()
		mat.albedo_color = color
		mat.roughness = 0.9
		var tex_paths: Dictionary = LAYER_TEXTURES.get(tex_name, LAYER_TEXTURES["loam"])
		var albedo_tex: Texture2D = load(tex_paths["albedo"])
		var normal_tex: Texture2D = load(tex_paths["normal"])
		if albedo_tex:
			mat.albedo_texture = albedo_tex
		if normal_tex:
			mat.normal_enabled = true
			mat.normal_texture = normal_tex
		mat.emission_enabled = true
		mat.emission = color
		mat.emission_energy_multiplier = 0.15
		mat.uv1_triplanar = true
		var mesh_inst := MeshInstance3D.new()
		mesh_inst.mesh = mesh
		mesh_inst.material_override = mat
		mesh_inst.position = Vector3(0, -(y_offset + h * 0.5), 0)
		container.add_child(mesh_inst)
		# Water level indicator: colored strip on visible faces
		if fill_frac > 0.01:
			_add_water_level(container, y_offset, h, fill_frac)
		y_offset += h


func _add_water_level(container: Node3D, y_offset: float, layer_h: float, fill_frac: float) -> void:
	## Render water fill as a semi-transparent box covering the bottom
	## portion of the layer, slightly larger so it protrudes on visible faces.
	var water_h: float = layer_h * fill_frac
	var layer_bottom: float = -(y_offset + layer_h)
	var water_mid_y: float = layer_bottom + water_h * 0.5
	var nudge := 0.003
	var water_mesh := BoxMesh.new()
	water_mesh.size = Vector3(CUTAWAY_WIDTH + nudge, water_h, CUTAWAY_DEPTH + nudge)
	var water_mat := StandardMaterial3D.new()
	var alpha: float = 0.35 + fill_frac * 0.35
	water_mat.albedo_color = Color(WATER_COLOR.r, WATER_COLOR.g, WATER_COLOR.b, alpha)
	water_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	water_mat.emission_enabled = true
	water_mat.emission = Color(0.25, 0.45, 0.85)
	water_mat.emission_energy_multiplier = 0.3
	var water_inst := MeshInstance3D.new()
	water_inst.mesh = water_mesh
	water_inst.material_override = water_mat
	water_inst.position = Vector3(0, water_mid_y, 0)
	container.add_child(water_inst)


func _build_roots(container: Node3D, profile_layers: Array, root_depth_cm: float) -> void:
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 30.0)
	var root_world: float = minf(root_depth_cm, total_depth) * SCALE_CM
	if root_world < 0.01:
		return
	# Taproot: vertical cylinder from surface down
	var tap := _create_tube(
		Vector3(0, 0, 0),
		Vector3(0, -root_world, 0),
		0.015,
		ROOT_COLOR,
	)
	container.add_child(tap)
	for frac in [0.33, 0.66]:
		var y: float = -root_world * frac
		var spread: float = CUTAWAY_WIDTH * 0.3
		for side in [-1.0, 1.0]:
			var lateral := _create_tube(
				Vector3(0, y, 0),
				Vector3(side * spread, y - 0.02, 0),
				0.008,
				ROOT_COLOR.darkened(frac * 0.3),
			)
			container.add_child(lateral)
			var sub_spread: float = spread * 0.5
			var sub := _create_tube(
				Vector3(side * spread, y - 0.02, 0),
				Vector3(side * (spread + sub_spread * 0.3), y - 0.06, side * 0.05),
				0.004,
				ROOT_COLOR.darkened(frac * 0.4),
			)
			container.add_child(sub)


func _build_info_labels(container: Node3D, profile_layers: Array, soil_state: Dictionary) -> void:
	var no3_arr: Array = soil_state.get("n_no3", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var som_labile: Array = soil_state.get("som_labile_c", [])
	var y_offset := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 30.0)
		var h: float = depth_cm * SCALE_CM
		var mid_y: float = -(y_offset + h * 0.5)
		var n_val: float = no3_arr[i] if i < no3_arr.size() else 0.0
		var p_val: float = p_arr[i] if i < p_arr.size() else 0.0
		var som_val: float = som_labile[i] if i < som_labile.size() else 0.0
		var label := Label3D.new()
		label.text = "N:%.1f P:%.1f SOM:%.0f" % [n_val, p_val, som_val]
		label.font_size = 32
		label.pixel_size = 0.002
		label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		label.modulate = Color(0.9, 0.9, 0.95)
		label.outline_size = 8
		label.outline_modulate = Color(0.1, 0.1, 0.15, 0.8)
		label.position = Vector3(CUTAWAY_WIDTH * 0.7, mid_y, 0)
		container.add_child(label)
		y_offset += h


static func _create_tube(from: Vector3, to: Vector3, radius: float, color: Color) -> MeshInstance3D:
	var dir := to - from
	var length: float = dir.length()
	if length < 0.001:
		return MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.top_radius = radius
	cyl.bottom_radius = radius * 0.7
	cyl.height = length
	cyl.radial_segments = 6
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.roughness = 0.8
	var inst := MeshInstance3D.new()
	inst.mesh = cyl
	inst.material_override = mat
	# Position at midpoint, orient along direction
	inst.position = from + dir * 0.5
	# Default cylinder is along Y. Rotate to align with direction.
	var up := Vector3.UP
	if absf(dir.normalized().dot(up)) > 0.99:
		inst.rotation = Vector3.ZERO
		if dir.y > 0:
			inst.rotation.z = PI
	else:
		inst.look_at_from_position(inst.position, to, up)
		inst.rotate_object_local(Vector3.RIGHT, PI * 0.5)
	return inst
