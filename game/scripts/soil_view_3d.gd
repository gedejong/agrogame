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
	var is_refresh: bool = _active and center_pos.is_equal_approx(_last_center_pos)
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
	if not is_refresh:
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


func _build_roots(container: Node3D, profile_layers: Array, root_depth_cm: float) -> void:
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 30.0)
	var root_world: float = minf(root_depth_cm, total_depth) * SCALE_CM
	if root_world < 0.01:
		return
	# Paint roots as a texture on the two visible pillar faces
	var total_h: float = total_depth * SCALE_CM
	var img := _generate_root_image(root_world, total_h)
	var tex := ImageTexture.create_from_image(img)
	# +X face (right side from above)
	_add_face_quad(container, tex, total_h, Vector3(CUTAWAY_WIDTH * 0.5 + 0.002, 0, 0), 0)
	# +Z face (front side from above)
	_add_face_quad(container, tex, total_h, Vector3(0, 0, CUTAWAY_DEPTH * 0.5 + 0.002), 1)


static func _add_face_quad(
	container: Node3D, tex: Texture2D, total_h: float, offset: Vector3, face: int
) -> void:
	var quad := QuadMesh.new()
	quad.size = Vector2(CUTAWAY_WIDTH, total_h)
	var mat := StandardMaterial3D.new()
	mat.albedo_texture = tex
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mat.no_depth_test = true
	var inst := MeshInstance3D.new()
	inst.mesh = quad
	inst.material_override = mat
	inst.position = offset + Vector3(0, -total_h * 0.5, 0)
	if face == 0:
		inst.rotation.y = PI * 0.5
	container.add_child(inst)


static func _root_hash(seed_val: int, idx: int) -> float:
	var h := (seed_val * 2654435761 + idx * 40503) & 0x7FFFFFFF
	return float(h % 1000) / 1000.0


static func _generate_root_image(root_depth: float, total_h: float) -> Image:
	## 4 root systems per face, matching 2D soil_view.gd approach.
	var w := 256
	var h := 512
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var root_px: int = int(root_depth / total_h * float(h))
	var depth_frac: float = clampf(root_depth / total_h, 0.0, 1.0)
	# 4 plants spaced at 1/8, 3/8, 5/8, 7/8 across the face
	var plant_xs: Array[int] = [w / 8, w * 3 / 8, w * 5 / 8, w * 7 / 8]
	for pi in range(plant_xs.size()):
		_draw_single_root_img(img, plant_xs[pi], root_px, depth_frac, pi)
	return img


static func _draw_single_root_img(
	img: Image, cx: int, root_px: int, depth_frac: float, seed_val: int
) -> void:
	var w: int = img.get_width()
	var tap_w: int = clampi(int(depth_frac * 4.0), 1, 4)
	var curve_x: int = int((_root_hash(seed_val, 0) - 0.5) * 8.0)
	var mid_y: int = root_px / 2
	var end_x: int = cx + int(float(curve_x) * 0.3)
	# Taproot
	_draw_line_img(img, cx, 2, cx + curve_x, mid_y, ROOT_COLOR, tap_w)
	_draw_line_img(img, cx + curve_x, mid_y, end_x, root_px, ROOT_COLOR.darkened(0.15), tap_w)
	# Lateral branches (3-6 per root)
	var num_b: int = 3 + int(_root_hash(seed_val, 1) * 4.0)
	for bi in range(num_b):
		var bd: float = _root_hash(seed_val, 10 + bi) * 0.85 + 0.08
		if bd > depth_frac:
			continue
		var by: int = int(float(root_px) * bd)
		var tap_at_x: int = int(lerpf(float(cx), float(end_x), bd))
		var spread: int = int((8.0 + _root_hash(seed_val, 20 + bi) * 16.0) * (1.0 - bd))
		var dir: int = 1 if _root_hash(seed_val, 30 + bi) > 0.4 else -1
		var dy: int = int((_root_hash(seed_val, 40 + bi) - 0.3) * 10.0)
		if spread < 3:
			continue
		var bx: int = clampi(tap_at_x + spread * dir, 2, w - 3)
		var bey: int = by + dy + 6
		var lat_w: int = clampi(int(3.0 * (1.0 - bd)), 2, 4)
		var lat_color := ROOT_COLOR.lightened(0.1).darkened(bd * 0.2)
		_draw_line_img(img, tap_at_x, by, bx, bey, lat_color, lat_w)
		# Sub-branches (1-2)
		var num_s: int = 1 + int(_root_hash(seed_val, 50 + bi) * 2.0)
		for si in range(num_s):
			var sf: float = 0.4 + _root_hash(seed_val, 60 + bi * 3 + si) * 0.4
			var sx: int = int(lerpf(float(tap_at_x), float(bx), sf))
			var sy: int = int(lerpf(float(by), float(bey), sf))
			var ss: int = int(float(spread) * (0.3 + _root_hash(seed_val, 70 + bi * 3 + si) * 0.3))
			var sd: int = dir if _root_hash(seed_val, 80 + bi * 3 + si) > 0.5 else -dir
			var sdy: int = 3 + int(_root_hash(seed_val, 90 + bi * 3 + si) * 6.0)
			var sex: int = clampi(sx + ss * sd, 2, w - 3)
			var sub_color := ROOT_COLOR.lightened(0.2).darkened(bd * 0.15)
			_draw_line_img(img, sx, sy, sex, sy + sdy, sub_color, 2)
			# Tiny rootlets — lighter, thinner
			if _root_hash(seed_val, 100 + bi * 3 + si) > 0.3:
				var rl_color := ROOT_COLOR.lightened(0.3)
				var rd: int = 1 if _root_hash(seed_val, 110 + bi * 3 + si) > 0.5 else -1
				var rx: int = clampi(sex + rd * 6, 2, w - 3)
				_draw_line_img(img, sex, sy + sdy, rx, sy + sdy + 6, rl_color, 1)
				# Second rootlet at different angle
				if _root_hash(seed_val, 120 + bi * 3 + si) > 0.4:
					var rx2: int = clampi(sex - rd * 4, 2, w - 3)
					_draw_line_img(img, sex, sy + sdy, rx2, sy + sdy + 5, rl_color, 1)


static func _draw_line_img(
	img: Image, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int
) -> void:
	## Bresenham line with thickness via filled circle at each pixel.
	var dx: int = absi(x1 - x0)
	var dy: int = absi(y1 - y0)
	var sx: int = 1 if x0 < x1 else -1
	var sy: int = 1 if y0 < y1 else -1
	var err: int = dx - dy
	var x := x0
	var y := y0
	var r: int = thickness / 2
	while true:
		for py in range(-r, r + 1):
			for px in range(-r, r + 1):
				var ix: int = x + px
				var iy: int = y + py
				if ix >= 0 and ix < img.get_width() and iy >= 0 and iy < img.get_height():
					img.set_pixel(ix, iy, color)
		if x == x1 and y == y1:
			break
		var e2: int = 2 * err
		if e2 > -dy:
			err -= dy
			x += sx
		if e2 < dx:
			err += dx
			y += sy


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
