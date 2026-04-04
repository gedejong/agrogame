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
var _layer_materials: Array[ShaderMaterial] = []
var _last_center_pos := Vector3.INF


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
	var center_pos := Vector3.ZERO
	if not columns.is_empty():
		center_pos = columns[0].get("pos", Vector3.ZERO)
	# Same tile refresh: animate water instead of rebuilding
	if _active and center_pos.is_equal_approx(_last_center_pos) and not _layer_materials.is_empty():
		_update_water_from_columns(columns)
		return
	_clear()
	_last_center_pos = center_pos
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
	# Opening animation: scale Y from 0 to 1
	scale = Vector3(1, 0, 1)
	var tween := create_tween()
	tween.set_ease(Tween.EASE_OUT)
	tween.set_trans(Tween.TRANS_BACK)
	tween.tween_property(self, "scale", Vector3(1, 1, 1), 0.4)


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
	_active = false
	_last_center_pos = Vector3.INF
	var tween := create_tween()
	tween.set_ease(Tween.EASE_IN)
	tween.set_trans(Tween.TRANS_BACK)
	tween.tween_property(self, "scale", Vector3(1, 0, 1), 0.3)
	tween.tween_callback(
		func() -> void:
			visible = false
			closed.emit()
	)


func is_active() -> bool:
	return _active


func _clear() -> void:
	_layer_materials.clear()
	for child in get_children():
		child.queue_free()


func _build_layers(container: Node3D, profile_layers: Array, soil_state: Dictionary) -> void:
	var shader: Shader = load("res://shaders/soil_cutaway.gdshader")
	var thetas: Array = soil_state.get("water_theta", [])
	var y_offset := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 30.0)
		var tex_name: String = layer.get("texture", "loam")
		var sat: float = layer.get("saturation", 0.4)
		var h: float = depth_cm * SCALE_CM
		var base_color: Color = LAYER_COLORS.get(tex_name, LAYER_COLORS["loam"])
		var darken: float = float(i) * 0.12
		var color := base_color.darkened(darken)
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill_frac: float = clampf(theta / maxf(sat, 0.01), 0.0, 1.0)
		var tex_paths: Dictionary = LAYER_TEXTURES.get(tex_name, LAYER_TEXTURES["loam"])
		var albedo_tex: Texture2D = load(tex_paths["albedo"])
		var normal_tex: Texture2D = load(tex_paths["normal"])
		var mat := ShaderMaterial.new()
		mat.shader = shader
		mat.set_shader_parameter("tint_color", color)
		mat.set_shader_parameter("water_fill", fill_frac)
		mat.set_shader_parameter("box_height", h)
		mat.set_shader_parameter("emission_strength", 0.35)
		if albedo_tex:
			mat.set_shader_parameter("albedo_texture", albedo_tex)
		if normal_tex:
			mat.set_shader_parameter("normal_texture", normal_tex)
		_layer_materials.append(mat)
		var mesh := BoxMesh.new()
		mesh.size = Vector3(CUTAWAY_WIDTH, h, CUTAWAY_DEPTH)
		var mesh_inst := MeshInstance3D.new()
		mesh_inst.mesh = mesh
		mesh_inst.material_override = mat
		mesh_inst.position = Vector3(0, -(y_offset + h * 0.5), 0)
		container.add_child(mesh_inst)
		y_offset += h


func _update_water_from_columns(columns: Array[Dictionary]) -> void:
	var fills: Array[float] = []
	for col_data: Dictionary in columns:
		var soil_state: Dictionary = col_data.get("soil_state", {})
		var profile: Array = col_data.get("profile", [])
		var thetas: Array = soil_state.get("water_theta", [])
		for i in range(profile.size()):
			var sat: float = profile[i].get("saturation", 0.4)
			var theta: float = thetas[i] if i < thetas.size() else 0.0
			fills.append(clampf(theta / maxf(sat, 0.01), 0.0, 1.0))
	_animate_water(fills)


func _animate_water(new_fills: Array[float]) -> void:
	## Tween water_fill uniforms for smooth animation.
	for i in range(mini(_layer_materials.size(), new_fills.size())):
		var mat: ShaderMaterial = _layer_materials[i]
		var tween := create_tween()
		tween.tween_method(
			func(val: float) -> void: mat.set_shader_parameter("water_fill", val),
			float(mat.get_shader_parameter("water_fill")),
			new_fills[i],
			0.4,
		)


func _build_roots(container: Node3D, profile_layers: Array, root_depth_cm: float) -> void:
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 30.0)
	var root_world: float = minf(root_depth_cm, total_depth) * SCALE_CM
	if root_world < 0.01:
		return
	# Draw roots on the camera-facing corner using line meshes
	var ox: float = CUTAWAY_WIDTH * 0.48
	var oz: float = CUTAWAY_DEPTH * 0.48
	# Taproot
	_add_root_line(container, [Vector3(ox, 0, oz), Vector3(ox, -root_world, oz)], ROOT_COLOR, 3.0)
	# Laterals at 1/4, 1/2, 3/4 depth
	for frac in [0.25, 0.5, 0.75]:
		var y: float = -root_world * frac
		var spread: float = CUTAWAY_WIDTH * 0.35
		for side in [-1.0, 1.0]:
			var tx: float = ox + side * spread
			var tz: float = oz + side * spread * 0.3
			_add_root_line(
				container,
				[Vector3(ox, y, oz), Vector3(tx, y - 0.03, tz)],
				ROOT_COLOR.darkened(frac * 0.3),
				2.0,
			)
			# Sub-branch
			_add_root_line(
				container,
				[Vector3(tx, y - 0.03, tz), Vector3(tx + side * spread * 0.2, y - 0.07, tz)],
				ROOT_COLOR.darkened(frac * 0.3 + 0.1),
				1.0,
			)
			# Fine rootlet
			_add_root_line(
				container,
				[Vector3(tx, y - 0.03, tz), Vector3(tx, y - 0.08, tz + side * 0.04)],
				ROOT_COLOR.darkened(frac * 0.3 + 0.15),
				0.7,
			)


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


static func _add_root_line(container: Node3D, points: Array, color: Color, width: float) -> void:
	var im := ImmediateMesh.new()
	im.surface_begin(Mesh.PRIMITIVE_LINE_STRIP)
	for pt: Vector3 in points:
		im.surface_add_vertex(pt)
	im.surface_end()
	var mat := StandardMaterial3D.new()
	mat.albedo_color = color
	mat.no_depth_test = true
	mat.emission_enabled = true
	mat.emission = color
	mat.emission_energy_multiplier = 0.4
	mat.point_size = width
	var inst := MeshInstance3D.new()
	inst.mesh = im
	inst.material_override = mat
	container.add_child(inst)
