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

## Per-crop root style: plants, tap_w, fibrous density (0-1), depth bias (higher=shallower)
const CROP_ROOT_STYLE := {
	"maize": {"plants": 4, "tap_w": 3, "density": 0.7, "shallow_bias": 0.4},
	"spring_wheat": {"plants": 10, "tap_w": 1, "density": 0.9, "shallow_bias": 0.6},
	"winter_wheat": {"plants": 10, "tap_w": 1, "density": 0.9, "shallow_bias": 0.6},
	"sorghum": {"plants": 4, "tap_w": 3, "density": 0.7, "shallow_bias": 0.35},
	"rice": {"plants": 8, "tap_w": 1, "density": 0.85, "shallow_bias": 0.7},
	"grape": {"plants": 2, "tap_w": 4, "density": 0.5, "shallow_bias": 0.3},
}
const CUTAWAY_WIDTH := 1.0
const CUTAWAY_DEPTH := 1.0

## cm → world units. Must match farm_view.METERS_PER_TILE.
const SCALE_CM := 0.005
const _SHADER := preload("res://shaders/soil_cutaway.gdshader")

var _active := false
var _layer_materials: Array[ShaderMaterial] = []
var _water_tweens: Array[Tween] = []
var _last_center_pos := Vector3.INF
var _flow_overlay: FlowOverlay = null
## Cached loaded textures keyed by path to avoid repeated load() calls.
var _tex_cache := {}


static func get_profile_layers(soil_type: String) -> Array:
	# Soil horizons: A (topsoil) → B (subsoil) → C (parent material)
	match soil_type:
		"sandy":
			return [
				{"depth_cm": 25, "texture": "sand", "saturation": 0.38},
				{"depth_cm": 35, "texture": "sand", "saturation": 0.37},
				{"depth_cm": 40, "texture": "clay", "saturation": 0.40},
			]
		"clay":
			return [
				{"depth_cm": 30, "texture": "loam", "saturation": 0.48},
				{"depth_cm": 35, "texture": "clay", "saturation": 0.54},
				{"depth_cm": 40, "texture": "clay", "saturation": 0.53},
			]
		_:
			return [
				{"depth_cm": 25, "texture": "loam", "saturation": 0.45},
				{"depth_cm": 35, "texture": "clay", "saturation": 0.44},
				{"depth_cm": 40, "texture": "loam", "saturation": 0.42},
			]


func show_cutaway(columns: Array[Dictionary]) -> void:
	## Each column: {pos: Vector3, soil_state: Dict, profile: Array,
	##   root_depth_cm: float, show_info: bool}
	var center_pos := Vector3.ZERO
	if not columns.is_empty():
		center_pos = columns[0].get("pos", Vector3.ZERO)
	var is_refresh: bool = _active and center_pos.is_equal_approx(_last_center_pos)
	if is_refresh:
		_refresh_water(columns)
		_refresh_roots_and_labels(columns)
		_update_flow_overlay(columns)
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
		_build_column(col_data, pos, soil_state, profile, rdcm, show_info)
	_update_flow_overlay(columns)
	visible = true
	_active = true
	scale = Vector3(1, 0, 1)
	var tween := create_tween()
	tween.set_ease(Tween.EASE_OUT)
	tween.set_trans(Tween.TRANS_BACK)
	tween.tween_property(self, "scale", Vector3(1, 1, 1), 0.4)


func _refresh_water(columns: Array[Dictionary]) -> void:
	# Kill any in-progress water tweens to prevent accumulation
	for tw: Tween in _water_tweens:
		if tw.is_valid():
			tw.kill()
	_water_tweens.clear()
	var mat_idx := 0
	for col_data: Dictionary in columns:
		var soil_state: Dictionary = col_data.get("soil_state", {})
		var profile: Array = col_data.get("profile", [])
		var thetas: Array = soil_state.get("water_theta", [])
		for i in range(profile.size()):
			if mat_idx >= _layer_materials.size():
				break
			var sat: float = profile[i].get("saturation", 0.4)
			var theta: float = thetas[i] if i < thetas.size() else 0.0
			var new_fill: float = clampf(theta / maxf(sat, 0.01), 0.0, 1.0)
			var mat: ShaderMaterial = _layer_materials[mat_idx]
			var old_fill: float = mat.get_shader_parameter("water_fill")
			if not is_equal_approx(old_fill, new_fill):
				var tw := create_tween()
				tw.tween_method(
					func(v: float) -> void: mat.set_shader_parameter("water_fill", v),
					old_fill,
					new_fill,
					0.4,
				)
				_water_tweens.append(tw)
			mat_idx += 1


func _refresh_roots_and_labels(columns: Array[Dictionary]) -> void:
	# Roots are shader-based: update layer material uniforms on refresh.
	if columns.is_empty():
		return
	var col_data: Dictionary = columns[0]
	var profile: Array = col_data.get("profile", [])
	var rdcm: float = col_data.get("root_depth_cm", 0.0)
	var crop_key: String = col_data.get("crop_key", "")
	_build_roots(profile, rdcm, crop_key)


func _update_flow_overlay(columns: Array[Dictionary]) -> void:
	if not _flow_overlay:
		_flow_overlay = FlowOverlay.new()
		add_child(_flow_overlay)
	# Debug test mode: show sample tubes instead of real data
	var debug_flow: bool = ProjectSettings.get_setting("agrogame/debug/flow_tubes_test", false)
	if debug_flow:
		var test_pos := Vector3.ZERO
		if not columns.is_empty():
			test_pos = columns[0].get("pos", Vector3.ZERO)
		_flow_overlay.show_test_tubes(test_pos)
		return
	if columns.is_empty():
		_flow_overlay.clear_tubes()
		return
	var center: Dictionary = columns[0]
	var events: Array = center.get("events", [])
	var profile: Array = center.get("profile", [])
	var pos: Vector3 = center.get("pos", Vector3.ZERO)
	print("[FLOW] events=%d profile=%d pos=%s" % [events.size(), profile.size(), str(pos)])
	_flow_overlay.update_from_events(events, profile, pos)
	print("[FLOW] tubes=%d" % _flow_overlay._tubes.size())


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
	_build_layers(container, profile_layers, soil_state, root_depth_cm, crop_key)
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
	_water_tweens.clear()
	for child in get_children():
		child.queue_free()
	_flow_overlay = null


func _build_layers(
	container: Node3D,
	profile_layers: Array,
	soil_state: Dictionary,
	root_depth_cm: float = 0.0,
	crop_key: String = "",
) -> void:
	var thetas: Array = soil_state.get("water_theta", [])
	# Generate root texture once for all layers
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 30.0)
	var root_tex: Texture2D = null
	if root_depth_cm > 0.0:
		var root_world: float = minf(root_depth_cm, total_depth) * SCALE_CM
		var total_h: float = total_depth * SCALE_CM
		var style: Dictionary = CROP_ROOT_STYLE.get(crop_key, CROP_ROOT_STYLE.get("maize", {}))
		var img := _generate_root_image(root_world, total_h, style)
		root_tex = ImageTexture.create_from_image(img)
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
		mat.set_shader_parameter("emission_strength", 0.1)
		if albedo_tex:
			mat.set_shader_parameter("albedo_texture", albedo_tex)
		if normal_tex:
			mat.set_shader_parameter("normal_texture", normal_tex)
		if root_tex:
			mat.set_shader_parameter("root_texture", root_tex)
			mat.set_shader_parameter("root_strength", 1.0)
		_layer_materials.append(mat)
		var mesh := BoxMesh.new()
		mesh.size = Vector3(CUTAWAY_WIDTH, h, CUTAWAY_DEPTH)
		var mesh_inst := MeshInstance3D.new()
		mesh_inst.mesh = mesh
		mesh_inst.material_override = mat
		mesh_inst.position = Vector3(0, -(y_offset + h * 0.5), 0)
		container.add_child(mesh_inst)
		y_offset += h


func _build_roots(profile_layers: Array, root_depth_cm: float, crop_key: String) -> void:
	# Roots are now rendered via the cutaway shader (root_texture + root_strength).
	# This function updates existing layer materials when roots change on refresh.
	if root_depth_cm <= 0.0:
		for mat in _layer_materials:
			mat.set_shader_parameter("root_strength", 0.0)
		return
	var total_depth := 0.0
	for layer: Dictionary in profile_layers:
		total_depth += layer.get("depth_cm", 30.0)
	var root_world: float = minf(root_depth_cm, total_depth) * SCALE_CM
	var total_h: float = total_depth * SCALE_CM
	var style: Dictionary = CROP_ROOT_STYLE.get(crop_key, CROP_ROOT_STYLE.get("maize", {}))
	var img := _generate_root_image(root_world, total_h, style)
	var tex := ImageTexture.create_from_image(img)
	for mat in _layer_materials:
		mat.set_shader_parameter("root_texture", tex)
		mat.set_shader_parameter("root_strength", 1.0)


static func _root_hash(seed_val: int, idx: int) -> float:
	var h := (seed_val * 2654435761 + idx * 40503) & 0x7FFFFFFF
	return float(h % 1000) / 1000.0


static func _generate_root_image(root_depth: float, total_h: float, style: Dictionary) -> Image:
	## Generate root texture using noise-based fibrous density + taproot lines.
	## Creates a dense, networky root mass that fills the rooted soil volume.
	var w := 256
	var h := 512
	var img := Image.create(w, h, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	var root_px: int = int(root_depth / total_h * float(h))
	if root_px < 2:
		return img
	var num_plants: int = style.get("plants", 4)
	var tap_w: int = style.get("tap_w", 2)
	var density: float = style.get("density", 0.7)
	var shallow_bias: float = style.get("shallow_bias", 0.5)

	# Noise layers for fibrous network
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise.frequency = 0.035
	noise.fractal_type = FastNoiseLite.FRACTAL_FBM
	noise.fractal_octaves = 4
	noise.fractal_lacunarity = 2.2
	noise.fractal_gain = 0.55
	# Ridged noise for vein-like branching structures
	var vein_noise := FastNoiseLite.new()
	vein_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	vein_noise.frequency = 0.02
	vein_noise.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	vein_noise.fractal_octaves = 5
	vein_noise.fractal_lacunarity = 2.0
	vein_noise.fractal_gain = 0.5
	vein_noise.seed = 17
	# Fine detail noise
	var fine_noise := FastNoiseLite.new()
	fine_noise.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	fine_noise.frequency = 0.08
	fine_noise.fractal_type = FastNoiseLite.FRACTAL_RIDGED
	fine_noise.fractal_octaves = 3
	fine_noise.seed = 42

	# Taproot X positions
	var tap_xs: Array[int] = []
	for pi in range(num_plants):
		tap_xs.append(int((float(pi) + 0.5) / float(num_plants) * float(w)))

	# Fill with noise-based root density
	for py in range(mini(root_px, h)):
		var depth_norm: float = float(py) / float(maxi(root_px, 1))
		# Dense near surface, fading toward root front
		var depth_fac: float = 1.0 - pow(depth_norm, 1.5 - shallow_bias)
		# Soft fade at root front (last 15%)
		var front_fade: float = 1.0
		if depth_norm > 0.85:
			front_fade = clampf((1.0 - depth_norm) / 0.15, 0.0, 1.0)
		for px in range(w):
			# Proximity to nearest taproot
			var min_dist: float = float(w)
			for tx: int in tap_xs:
				var d: float = absf(float(px - tx))
				if d < min_dist:
					min_dist = d
			var prox: float = clampf(1.0 - min_dist / (float(w) * 0.3), 0.0, 1.0)
			# Noise layers
			var n1: float = noise.get_noise_2d(float(px), float(py)) * 0.5 + 0.5
			var n3: float = vein_noise.get_noise_2d(float(px), float(py))
			var n2: float = fine_noise.get_noise_2d(float(px), float(py))
			# Vein threshold: branching structures
			var vein: float = clampf(1.0 - absf(n3) * 3.0, 0.0, 1.0)
			var base_val: float = (prox * 0.4 + n1 * 0.3 + vein * 0.3) * density
			base_val *= depth_fac * front_fade
			# Fine rootlets near taproots
			var fine_val: float = clampf(n2 * 2.0, 0.0, 1.0) * 0.3 * prox
			var total: float = clampf(base_val + fine_val, 0.0, 1.0)
			# Threshold for distinct root strands
			if total > 0.35:
				var alpha: float = clampf((total - 0.35) / 0.45, 0.0, 1.0)
				var col := ROOT_COLOR.darkened(depth_norm * 0.2)
				col.a = alpha
				img.set_pixel(px, py, col)

	# Draw taproots on top as distinct stems
	for pi in range(num_plants):
		var cx: int = tap_xs[pi]
		var wobble: int = int((_root_hash(pi, 0) - 0.5) * 8.0)
		var end_x: int = cx + int(float(wobble) * 0.3)
		_draw_line_img(img, cx, 0, end_x, root_px, ROOT_COLOR, tap_w)
	return img


static func _draw_line_img(
	img: Image, x0: int, y0: int, x1: int, y1: int, color: Color, thickness: int
) -> void:
	## Bresenham line with thickness.
	var dx: int = absi(x1 - x0)
	var dy: int = absi(y1 - y0)
	var sx: int = 1 if x0 < x1 else -1
	var sy: int = 1 if y0 < y1 else -1
	var err: int = dx - dy
	var x := x0
	var y := y0
	var r: int = thickness / 2
	while true:
		for tpy in range(-r, r + 1):
			for tpx in range(-r, r + 1):
				var ix: int = x + tpx
				var iy: int = y + tpy
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


func _build_info_labels(
	_container: Node3D, _profile_layers: Array, _soil_state: Dictionary
) -> void:
	# Info display is now handled by the 2D nutrient_panel.gd on CanvasLayer.
	# This function is kept for interface compatibility but does nothing.
	pass
