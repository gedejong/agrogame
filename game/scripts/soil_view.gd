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

## Per-crop root style: {plants_per_face, tap_thickness, lateral_thickness, max_branches}
const CROP_ROOT_STYLE := {
	"maize": {"plants": 4, "tap_w": 3, "lat_w": 2, "branches": 5},
	"spring_wheat": {"plants": 10, "tap_w": 1, "lat_w": 1, "branches": 3},
	"winter_wheat": {"plants": 10, "tap_w": 1, "lat_w": 1, "branches": 3},
	"sorghum": {"plants": 4, "tap_w": 3, "lat_w": 2, "branches": 6},
	"rice": {"plants": 8, "tap_w": 1, "lat_w": 1, "branches": 2},
	"grape": {"plants": 2, "tap_w": 4, "lat_w": 3, "branches": 4},
}
const CUTAWAY_WIDTH := 1.0
const CUTAWAY_DEPTH := 1.0

## Nutrient bar display: color-blind safe palette (ColorBrewer + art guide UI accents)
## Each entry: {color, max_val, optimal_min, optimal_max, unit, label}
const NUTRIENT_BARS := {
	"NO3":
	{"color": Color(0.17, 0.63, 0.17), "max": 5.0, "opt_min": 1.0, "opt_max": 5.0, "unit": "g/m²"},
	"NH4":
	{"color": Color(0.6, 0.87, 0.54), "max": 3.0, "opt_min": 0.3, "opt_max": 3.0, "unit": "g/m²"},
	"P":
	{"color": Color(0.58, 0.4, 0.74), "max": 2.0, "opt_min": 0.2, "opt_max": 2.0, "unit": "g/m²"},
	"SOM":
	{
		"color": Color(0.55, 0.34, 0.29),
		"max": 500.0,
		"opt_min": 50.0,
		"opt_max": 500.0,
		"unit": "g/m²"
	},
	"Water":
	{
		"color": Color(0.12, 0.47, 0.71),
		"max": 0.45,
		"opt_min": 0.08,
		"opt_max": 0.35,
		"unit": "m³/m³"
	},
	"pH": {"color": Color(0.5, 0.5, 0.5), "max": 9.0, "opt_min": 5.5, "opt_max": 7.5, "unit": ""},
	"Microbe":
	{"color": Color(1.0, 0.5, 0.05), "max": 50.0, "opt_min": 5.0, "opt_max": 50.0, "unit": "gC/m²"},
}
const BAR_STRESS_COLOR := Color(0.9, 0.25, 0.2)
const BAR_MARGINAL_COLOR := Color(0.95, 0.75, 0.2)
const BAR_WIDTH := 0.008
const BAR_MAX_LENGTH := 0.15
const BAR_SPACING := 0.012
const CONNECTOR_RADIUS := 0.001
## cm → world units. Must match farm_view.METERS_PER_TILE.
const SCALE_CM := 0.005
const _SHADER := preload("res://shaders/soil_cutaway.gdshader")

var _active := false
var _layer_materials: Array[ShaderMaterial] = []
var _last_center_pos := Vector3.INF
## Cached loaded textures keyed by path to avoid repeated load() calls.
var _tex_cache := {}


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
		_build_column(col_data, pos, soil_state, profile, rdcm, show_info)
	visible = true
	_active = true
	if not is_refresh:
		scale = Vector3(1, 0, 1)
		var tween := create_tween()
		tween.set_ease(Tween.EASE_OUT)
		tween.set_trans(Tween.TRANS_BACK)
		tween.tween_property(self, "scale", Vector3(1, 1, 1), 0.4)


func _build_column(
	col_data: Dictionary,
	pos: Vector3,
	soil_state: Dictionary,
	profile_layers: Array,
	root_depth_cm: float,
	show_info: bool,
) -> void:
	var container := Node3D.new()
	container.position = Vector3(pos.x, pos.y - 0.005, pos.z)
	var crop_key: String = col_data.get("crop_key", "")
	_build_layers(container, profile_layers, soil_state)
	if root_depth_cm > 0.0:
		_build_roots(container, profile_layers, root_depth_cm, crop_key)
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


func _cached_tex(path: String) -> Texture2D:
	if not _tex_cache.has(path):
		_tex_cache[path] = load(path)
	return _tex_cache[path]


func is_active() -> bool:
	return _active


func _clear() -> void:
	_layer_materials.clear()
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
		var darken: float = float(i) * 0.12
		var color := base_color.darkened(darken)
		var theta: float = thetas[i] if i < thetas.size() else 0.0
		var fill_frac: float = clampf(theta / maxf(sat, 0.01), 0.0, 1.0)
		var tex_paths: Dictionary = LAYER_TEXTURES.get(tex_name, LAYER_TEXTURES["loam"])
		var albedo_tex: Texture2D = _cached_tex(tex_paths["albedo"])
		var normal_tex: Texture2D = _cached_tex(tex_paths["normal"])
		var mat := ShaderMaterial.new()
		mat.shader = _SHADER
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


func _build_roots(
	container: Node3D, profile_layers: Array, root_depth_cm: float, crop_key: String
) -> void:
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 30.0)
	var root_world: float = minf(root_depth_cm, total_depth) * SCALE_CM
	if root_world < 0.01:
		return
	var total_h: float = total_depth * SCALE_CM
	var style: Dictionary = CROP_ROOT_STYLE.get(crop_key, CROP_ROOT_STYLE.get("maize", {}))
	var img := _generate_root_image(root_world, total_h, style)
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


static func _generate_root_image(root_depth: float, total_h: float, style: Dictionary) -> Image:
	## Root systems per face, density matching the crop above.
	var w := 256
	var h := 512
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var root_px: int = int(root_depth / total_h * float(h))
	var depth_frac: float = clampf(root_depth / total_h, 0.0, 1.0)
	var num_plants: int = style.get("plants", 4)
	var tap_w: int = style.get("tap_w", 2)
	var lat_w: int = style.get("lat_w", 1)
	var max_branches: int = style.get("branches", 4)
	for pi in range(num_plants):
		var cx: int = int((float(pi) + 0.5) / float(num_plants) * float(w))
		_draw_single_root_img(img, cx, root_px, depth_frac, pi, tap_w, lat_w, max_branches)
	return img


static func _draw_single_root_img(
	img: Image,
	cx: int,
	root_px: int,
	depth_frac: float,
	seed_val: int,
	tap_w: int = 3,
	lat_w: int = 2,
	max_branches: int = 5,
) -> void:
	## Draw one root system. Uses monotonic hash counter (hi) to avoid collisions.
	var w: int = img.get_width()
	var hi := 0
	var curve_x: int = int((_root_hash(seed_val, hi) - 0.5) * 8.0)
	hi += 1
	var mid_y: int = root_px / 2
	var end_x: int = cx + int(float(curve_x) * 0.3)
	_draw_line_img(img, cx, 2, cx + curve_x, mid_y, ROOT_COLOR, tap_w)
	_draw_line_img(img, cx + curve_x, mid_y, end_x, root_px, ROOT_COLOR.darkened(0.15), tap_w)
	var num_b: int = maxi(1, int(_root_hash(seed_val, hi) * float(max_branches)))
	hi += 1
	for bi in range(num_b):
		var bd: float = _root_hash(seed_val, hi) * 0.85 + 0.08
		hi += 1
		if bd > depth_frac:
			continue
		var by: int = int(float(root_px) * bd)
		var tap_at_x: int = int(lerpf(float(cx), float(end_x), bd))
		var spread: int = int((8.0 + _root_hash(seed_val, hi) * 16.0) * (1.0 - bd))
		hi += 1
		var dir: int = 1 if _root_hash(seed_val, hi) > 0.4 else -1
		hi += 1
		var dy: int = int((_root_hash(seed_val, hi) - 0.3) * 10.0)
		hi += 1
		if spread < 3:
			continue
		var bx: int = clampi(tap_at_x + spread * dir, 2, w - 3)
		var bey: int = by + dy + 6
		var lw: int = clampi(int(float(lat_w) * (1.0 - bd) + 0.5), 1, lat_w)
		_draw_line_img(img, tap_at_x, by, bx, bey, ROOT_COLOR.lightened(0.1).darkened(bd * 0.2), lw)
		var num_s: int = 1 + int(_root_hash(seed_val, hi) * 2.0)
		hi += 1
		for si in range(num_s):
			var sf: float = 0.4 + _root_hash(seed_val, hi) * 0.4
			hi += 1
			var sx: int = int(lerpf(float(tap_at_x), float(bx), sf))
			var sy: int = int(lerpf(float(by), float(bey), sf))
			var ss: int = int(float(spread) * (0.3 + _root_hash(seed_val, hi) * 0.3))
			hi += 1
			var sd: int = dir if _root_hash(seed_val, hi) > 0.5 else -dir
			hi += 1
			var sdy: int = 3 + int(_root_hash(seed_val, hi) * 6.0)
			hi += 1
			var sex: int = clampi(sx + ss * sd, 2, w - 3)
			_draw_line_img(
				img, sx, sy, sex, sy + sdy, ROOT_COLOR.lightened(0.2).darkened(bd * 0.15), 2
			)
			var rl_color := ROOT_COLOR.lightened(0.3)
			for ri in range(3):
				if _root_hash(seed_val, hi) > 0.25:
					hi += 1
					var rd: int = 1 if _root_hash(seed_val, hi) > 0.5 else -1
					hi += 1
					var rl_dx: int = int((_root_hash(seed_val, hi) - 0.3) * 10.0) * rd
					hi += 1
					var rl_dy: int = 3 + int(_root_hash(seed_val, hi) * 8.0)
					hi += 1
					var rx: int = clampi(sex + rl_dx, 2, w - 3)
					_draw_line_img(img, sex, sy + sdy, rx, sy + sdy + rl_dy, rl_color, 1)
				else:
					hi += 4
			# Rootlets from lateral midpoint
			if _root_hash(seed_val, hi) > 0.3:
				hi += 1
				var mid_lx: int = (tap_at_x + bx) / 2
				var mid_ly: int = (by + bey) / 2
				var mrd: int = 1 if _root_hash(seed_val, hi) > 0.5 else -1
				hi += 1
				var mrx: int = clampi(mid_lx + mrd * 5, 2, w - 3)
				_draw_line_img(img, mid_lx, mid_ly, mrx, mid_ly + 6, rl_color, 1)
			else:
				hi += 2


static func _draw_line_img(
	img: Image, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int
) -> void:
	## Bresenham line with thickness via square stamp at each pixel.
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
	var nh4_arr: Array = soil_state.get("n_nh4", [])
	var p_arr: Array = soil_state.get("p_available", [])
	var som_labile: Array = soil_state.get("som_labile_c", [])
	var theta_arr: Array = soil_state.get("water_theta", [])
	var ph_arr: Array = soil_state.get("ph", [])
	var microbe_arr: Array = soil_state.get("microbe_c", [])
	var y_offset := 0.0
	for i in range(profile_layers.size()):
		var layer: Dictionary = profile_layers[i]
		var depth_cm: float = layer.get("depth_cm", 30.0)
		var h: float = depth_cm * SCALE_CM
		var mid_y: float = -(y_offset + h * 0.5)
		# Collect per-layer values
		var vals := {
			"NO3": no3_arr[i] if i < no3_arr.size() else 0.0,
			"NH4": nh4_arr[i] if i < nh4_arr.size() else 0.0,
			"P": p_arr[i] if i < p_arr.size() else 0.0,
			"SOM": som_labile[i] if i < som_labile.size() else 0.0,
			"Water": theta_arr[i] if i < theta_arr.size() else 0.0,
			"pH": ph_arr[i] if i < ph_arr.size() else 6.5,
			"Microbe": microbe_arr[i] if i < microbe_arr.size() else 0.0,
		}
		# Connector line from layer to info panel
		var panel_x: float = CUTAWAY_WIDTH * 0.6
		_add_connector(
			container, Vector3(CUTAWAY_WIDTH * 0.5, mid_y, 0), Vector3(panel_x, mid_y, 0)
		)
		# Build bars + label
		_build_bar_panel(container, vals, Vector3(panel_x, mid_y, 0))
		y_offset += h


func _add_connector(container: Node3D, from: Vector3, to: Vector3) -> void:
	var length: float = (to - from).length()
	if length < 0.001:
		return
	var line := MeshInstance3D.new()
	var cyl := CylinderMesh.new()
	cyl.height = length
	cyl.top_radius = CONNECTOR_RADIUS
	cyl.bottom_radius = CONNECTOR_RADIUS
	cyl.radial_segments = 4
	line.mesh = cyl
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.6, 0.6, 0.65, 0.6)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	line.material_override = mat
	line.position = (from + to) * 0.5
	line.rotation.z = PI * 0.5
	container.add_child(line)


func _build_bar_panel(container: Node3D, vals: Dictionary, pos: Vector3) -> void:
	var bar_idx := 0
	var text_parts: PackedStringArray = PackedStringArray()
	for key: String in NUTRIENT_BARS:
		var cfg: Dictionary = NUTRIENT_BARS[key]
		var val: float = vals.get(key, 0.0)
		var bar_y: float = pos.y + (float(bar_idx) - 3.0) * BAR_SPACING
		# Normalized bar length
		var max_val: float = cfg["max"]
		var bar_frac: float = clampf(val / maxf(max_val, 0.001), 0.0, 1.0)
		var bar_len: float = BAR_MAX_LENGTH * bar_frac
		# Stress coloring: green if optimal, yellow if marginal, red if deficient/excess
		var bar_color: Color = cfg["color"]
		var opt_min: float = cfg["opt_min"]
		var opt_max: float = cfg["opt_max"]
		if key == "pH":
			# pH: stress at both extremes
			if val < opt_min - 1.0 or val > opt_max + 1.0:
				bar_color = BAR_STRESS_COLOR
			elif val < opt_min or val > opt_max:
				bar_color = BAR_MARGINAL_COLOR
		else:
			if val < opt_min * 0.3:
				bar_color = BAR_STRESS_COLOR
			elif val < opt_min:
				bar_color = BAR_MARGINAL_COLOR
		# Bar mesh
		if bar_len > 0.001:
			var bar := MeshInstance3D.new()
			var box := BoxMesh.new()
			box.size = Vector3(bar_len, BAR_WIDTH, BAR_WIDTH)
			bar.mesh = box
			var mat := StandardMaterial3D.new()
			mat.albedo_color = bar_color
			mat.emission_enabled = true
			mat.emission = bar_color
			mat.emission_energy_multiplier = 0.2
			bar.material_override = mat
			bar.position = Vector3(pos.x + bar_len * 0.5, bar_y, pos.z)
			container.add_child(bar)
		# Collect text for label
		var unit: String = cfg["unit"]
		if key == "pH":
			text_parts.append("%s:%.1f" % [key, val])
		elif val >= 10.0:
			text_parts.append("%s:%.0f%s" % [key, val, unit])
		else:
			text_parts.append("%s:%.1f%s" % [key, val, unit])
		bar_idx += 1
	# Summary label
	var label := Label3D.new()
	label.text = " ".join(text_parts)
	label.font_size = 24
	label.pixel_size = 0.0015
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.modulate = Color(0.9, 0.9, 0.95)
	label.outline_size = 6
	label.outline_modulate = Color(0.1, 0.1, 0.15, 0.8)
	label.position = Vector3(pos.x + BAR_MAX_LENGTH + 0.02, pos.y, pos.z)
	container.add_child(label)
