extends Node3D
## 3D farm view — Phase 2 of 2D→3D migration (ADR-007).
## Renders 6x6 tile grid as MeshInstance3D with soil PBR shader.
## Crop billboard sprites (Sprite3D) per tile.
## Raycast click detection, SOM/moisture shader updates from API.

const GRID_COLS := 6
const GRID_ROWS := 6
const TILE_SIZE := 1.0
const TILE_HEIGHT := 0.1
## How many real-world meters one tile represents.
## Crop heights and soil depths are divided by this to get world units.
const METERS_PER_TILE := 2.0

const SOIL_TYPES: Array[String] = ["sandy", "organic", "clay"]
const SOIL_TEXTURES := {
	"sandy":
	{
		"albedo": "res://assets/textures/soil_sandy_albedo.png",
		"normal": "res://assets/textures/soil_sandy_normal.png",
	},
	"organic":
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

const SOM_MAX_C_G_M2 := 5000.0
const THETA_SATURATED := 0.45
const AVAILABLE_CROPS: Array[String] = ["maize", "spring_wheat", "sorghum", "rice", "grape"]
const CROP_GRID := {
	"maize": Vector2i(3, 8),
	"spring_wheat": Vector2i(10, 40),
	"winter_wheat": Vector2i(10, 40),
	"sorghum": Vector2i(3, 10),
	"rice": Vector2i(10, 8),
	"grape": Vector2i(2, 2),
}

const CropRenderer = preload("res://scripts/crop_renderer.gd")
const SoilView3D = preload("res://scripts/soil_view_3d.gd")
const MaizeRenderer3D = preload("res://scripts/maize_renderer_3d.gd")
const WheatRenderer3D = preload("res://scripts/wheat_renderer_3d.gd")
const SorghumRenderer3D = preload("res://scripts/sorghum_renderer_3d.gd")
const RiceRenderer3D = preload("res://scripts/rice_renderer_3d.gd")
const GrapeRenderer3D = preload("res://scripts/grape_renderer_3d.gd")
const CropRenderer3D = preload("res://scripts/crop_renderer_3d.gd")

const _STAGE_MAP := {
	"planted": 1,
	"emerged": 1,
	"vegetative": 2,
	"flowering": 3,
	"grain_fill": 4,
	"maturity": 4,
}

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_meshes: Array[MeshInstance3D] = []
var _tile_data: Array[Dictionary] = []
var _tile_materials: Array[ShaderMaterial] = []
var _crop_sprites: Array[Array] = []
var _crop_popup: PopupMenu = null
var _soil_view: Node3D = null
var _hidden_tiles: Array[int] = []
var _api_client: Node
var _last_step_data: Dictionary = {}

@onready var camera_rig: Node3D = $CameraRig
@onready var camera: Camera3D = $CameraRig/Camera3D
@onready var tile_root: Node3D = $TileRoot
@onready var crop_root: Node3D = $CropRoot
@onready var rain: GPUParticles3D = $Rain
@onready var fog_clouds: GPUParticles3D = $FogClouds
@onready var sun: DirectionalLight3D = $DirectionalLight3D
@onready var env: WorldEnvironment = $WorldEnvironment
@onready var status_label: Label = $UILayer/StatusLabel
@onready var date_label: Label = $UILayer/TopBar/DateLabel
@onready var credits_label: Label = $UILayer/TopBar/CreditsLabel
@onready var weather_label: Label = $UILayer/TopBar/WeatherLabel
@onready var weather_icon: TextureRect = $UILayer/TopBar/WeatherIcon
@onready var next_day_btn: Button = $UILayer/ActionBar/NextDayButton
@onready var ff7_btn: Button = $UILayer/ActionBar/FastForward7
@onready var ff_all_btn: Button = $UILayer/ActionBar/FastForwardAll
@onready var irrigate_btn: Button = $UILayer/ActionBar/IrrigateButton
@onready var fertilize_btn: Button = $UILayer/ActionBar/FertilizeButton
@onready var plant_btn: Button = $UILayer/ActionBar/PlantButton
@onready var soil_view_btn: Button = $UILayer/ActionBar/SoilViewButton
@onready var forecast_panel: VBoxContainer = $UILayer/ForecastPanel


func _ready() -> void:
	_api_client = preload("res://scripts/api_client.gd").new()
	add_child(_api_client)
	if GameState.game_id != "":
		_game_id = GameState.game_id
	next_day_btn.pressed.connect(_on_next_day)
	ff7_btn.pressed.connect(_on_ff7)
	ff_all_btn.pressed.connect(_on_ff_all)
	irrigate_btn.pressed.connect(_on_irrigate)
	fertilize_btn.pressed.connect(_on_fertilize)
	plant_btn.pressed.connect(_on_plant_pressed)
	soil_view_btn.pressed.connect(_on_soil_view)
	_setup_crop_popup()
	_build_tile_grid()
	status_label.text = "3D view — click tile to select"
	# Debug auto-start: create game, step 7 days, select tile, open cutaway
	var debug_auto: bool = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	if debug_auto:
		_debug_auto_start()


func _build_tile_grid() -> void:
	var shader: Shader = load("res://shaders/soil_tile.gdshader")
	var box := PlaneMesh.new()
	box.size = Vector2(TILE_SIZE, TILE_SIZE)
	# Center grid at origin
	var offset_x: float = (GRID_COLS - 1) * TILE_SIZE / 2.0
	var offset_z: float = (GRID_ROWS - 1) * TILE_SIZE / 2.0
	for row in range(GRID_ROWS):
		for col in range(GRID_COLS):
			var soil_type := _soil_type_for(col)
			var mat := ShaderMaterial.new()
			mat.shader = shader
			var tex_paths: Dictionary = SOIL_TEXTURES[soil_type]
			var albedo_tex: Texture2D = load(tex_paths["albedo"])
			var normal_tex: Texture2D = load(tex_paths["normal"])
			if albedo_tex:
				mat.set_shader_parameter("albedo_texture", albedo_tex)
			if normal_tex:
				mat.set_shader_parameter("normal_texture", normal_tex)
			mat.set_shader_parameter("som_frac", 0.0)
			mat.set_shader_parameter("moisture_frac", 0.0)
			mat.set_shader_parameter("selected", 0.0)
			var mesh_inst := MeshInstance3D.new()
			mesh_inst.mesh = box
			mesh_inst.material_override = mat
			mesh_inst.position = Vector3(
				col * TILE_SIZE - offset_x,
				0.0,
				row * TILE_SIZE - offset_z,
			)
			# StaticBody3D for raycast hit detection
			var body := StaticBody3D.new()
			var shape := CollisionShape3D.new()
			var box_shape := BoxShape3D.new()
			box_shape.size = Vector3(TILE_SIZE, 0.01, TILE_SIZE)
			shape.shape = box_shape
			body.add_child(shape)
			body.set_meta("tile_col", col)
			body.set_meta("tile_row", row)
			mesh_inst.add_child(body)
			tile_root.add_child(mesh_inst)
			_tile_meshes.append(mesh_inst)
			_tile_materials.append(mat)
			# 3D crop container — plants rebuilt per crop type
			var crop_container := Node3D.new()
			crop_container.position = mesh_inst.position
			crop_root.add_child(crop_container)
			_crop_sprites.append([crop_container])
			(
				_tile_data
				. append(
					{
						"col": col,
						"row": row,
						"soil_type": soil_type,
						"crop_key": "",
						"crop_stage": 0,
						"lai": 0.0,
						"stress": 0,
						"som_total_c_g_m2": 0.0,
						"theta_surface": 0.0,
					}
				)
			)


static func _soil_type_for(col: int) -> String:
	if col < 2:
		return "sandy"
	if col >= 4:
		return "clay"
	return "organic"


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			_handle_click(mb.position)
	elif event is InputEventKey:
		var ke := event as InputEventKey
		if ke.pressed and ke.keycode == KEY_ESCAPE:
			_hide_soil_cutaway()


func _handle_click(screen_pos: Vector2) -> void:
	var from := camera.project_ray_origin(screen_pos)
	var dir := camera.project_ray_normal(screen_pos)
	var space := get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(from, from + dir * 100.0)
	var result := space.intersect_ray(query)
	if result.is_empty():
		_deselect()
		return
	var collider: Object = result.get("collider")
	if collider and collider.has_meta("tile_col"):
		var col: int = collider.get_meta("tile_col")
		var row: int = collider.get_meta("tile_row")
		_select_tile(col, row)
	else:
		_deselect()


func _select_tile(col: int, row: int) -> void:
	_deselect()
	_selected_tile = Vector2i(col, row)
	var idx := row * GRID_COLS + col
	_tile_materials[idx].set_shader_parameter("selected", 1.0)
	var data: Dictionary = _tile_data[idx]
	var crop_key: String = data.get("crop_key", "")
	var crop_info := " | %s" % crop_key if not crop_key.is_empty() else ""
	status_label.text = (
		"[%d,%d] %s%s | SOM %.0f | θ %.2f"
		% [
			col,
			row,
			data["soil_type"],
			crop_info,
			data.get("som_total_c_g_m2", 0.0),
			data.get("theta_surface", 0.0),
		]
	)


func _deselect() -> void:
	if _selected_tile.x >= 0:
		var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
		_tile_materials[idx].set_shader_parameter("selected", 0.0)
	_selected_tile = Vector2i(-1, -1)


func _update_tile_shader(idx: int) -> void:
	var data: Dictionary = _tile_data[idx]
	var som_frac: float = clampf(data.get("som_total_c_g_m2", 0.0) / SOM_MAX_C_G_M2, 0.0, 1.0)
	var moisture_frac: float = clampf(data.get("theta_surface", 0.0) / THETA_SATURATED, 0.0, 1.0)
	_tile_materials[idx].set_shader_parameter("som_frac", som_frac)
	_tile_materials[idx].set_shader_parameter("moisture_frac", moisture_frac)


func _update_weather_lighting(weather: Dictionary) -> void:
	## Adjust sun, ambient, and fog based on weather conditions.
	var rain_mm: float = weather.get("rain_mm", 0.0)
	var tmin: float = weather.get("tmin_c", 10.0)
	var tmax: float = weather.get("tmax_c", 20.0)
	var overcast: float = clampf(rain_mm / 10.0, 0.0, 1.0)
	# Approximate humidity: high rain + small temp spread + cool = humid/foggy.
	# Wet-bulb depression proxy: large tmax-tmin = dry, small = humid.
	var temp_spread: float = maxf(tmax - tmin, 1.0)
	# Intentionally produces nonzero humidity on dry days with small temp spread
	# (e.g., calm overcast mornings with dew) — this creates subtle ground fog.
	var humidity_proxy: float = clampf((rain_mm / 5.0) + (1.0 - temp_spread / 15.0) * 0.5, 0.0, 1.0)
	# Sun: dim and cool on rainy days
	var sunny_color := Color(0.95, 0.9, 0.8)
	var overcast_color := Color(0.65, 0.65, 0.7)
	sun.light_color = sunny_color.lerp(overcast_color, overcast)
	sun.light_energy = lerpf(1.15, 0.5, overcast)
	var e := env.environment
	if not e:
		return
	# Ambient: slightly brighter on overcast (diffuse sky), but greyer
	e.ambient_light_energy = lerpf(0.4, 0.5, overcast)
	var amb_sunny := Color(0.4, 0.42, 0.5)
	var amb_overcast := Color(0.3, 0.3, 0.35)
	e.ambient_light_color = amb_sunny.lerp(amb_overcast, overcast)
	# Fog: driven by humidity proxy, not just rain
	e.fog_density = lerpf(0.001, 0.012, humidity_proxy)
	# Animated fog wisps
	fog_clouds.set_fog_intensity(humidity_proxy)


func _update_crop_visuals(idx: int) -> void:
	var data: Dictionary = _tile_data[idx]
	var crop_key: String = data.get("crop_key", "")
	var stage: int = data.get("crop_stage", 0)
	var lai: float = data.get("lai", 0.0)
	var stress: int = data.get("stress", 0)
	var grain: float = data.get("grain_g_m2", 0.0)
	var plants: Array = _crop_sprites[idx]
	# Compute growth parameters
	var lai_frac: float = clampf(lai / 6.0, 0.0, 1.0)
	var grain_frac: float = clampf(grain / 800.0, 0.0, 1.0)
	var growth: float = 0.0
	match stage:
		1:
			growth = 0.25
		2:
			growth = clampf(0.3 + lai_frac * 0.5, 0.3, 0.8)
		3:
			growth = 0.9
		4:
			growth = 1.0
	var expected_lai: float = 1.0
	match stage:
		2:
			expected_lai = 4.0
		3:
			expected_lai = 5.5
		4:
			expected_lai = 3.0
	var senescence: float = clampf(1.0 - lai / maxf(expected_lai, 0.1), 0.0, 1.0)
	if stage <= 2:
		senescence = 0.0
	var stress_f: float = 0.0
	if stress == 1:
		stress_f = 0.5
	elif stress == 2:
		stress_f = 0.3
	# plants[0] is the crop container for this tile
	var container: Node3D = plants[0]
	# Clear all previous plant geometry
	for child in container.get_children():
		child.queue_free()
	if stage == 0 or crop_key.is_empty():
		return
	# Build plant grid based on crop-specific density
	var grid: Vector2i = CROP_GRID.get(crop_key, Vector2i(4, 4))
	var total_plants: int = grid.x * grid.y
	var col: int = _tile_data[idx]["col"]
	var row: int = _tile_data[idx]["row"]
	var s: float = 1.0 / METERS_PER_TILE
	if total_plants > 50:
		# High density: single baked mesh per tile for performance
		_build_baked_plants(
			container, crop_key, grid, col, row, s, growth, senescence, stress_f, grain_frac
		)
	else:
		# Low density: individual Node3D plants
		for hi in range(grid.x):
			var u: float = (float(hi) + 0.5) / float(grid.x)
			for vi in range(grid.y):
				var v: float = (float(vi) + 0.5) / float(grid.y)
				var lx: float = (u - 0.5) * TILE_SIZE
				var lz: float = (v - 0.5) * TILE_SIZE
				var sv: int = col * 7 + row * 13 + hi * 3 + vi * 5
				var jm: float = TILE_SIZE / float(grid.x) * 0.1
				var jx: float = (fmod(float(sv % 7), 3.0) - 1.5) * jm
				var jz: float = (fmod(float((sv * 3) % 5), 2.0) - 1.0) * jm
				var new_plant := _create_3d_plant(
					crop_key, growth, senescence, stress_f, grain_frac, sv
				)
				new_plant.scale = Vector3(s, s, s)
				new_plant.position = Vector3(lx + jx, 0, lz + jz)
				container.add_child(new_plant)


func _build_baked_plants(
	container: Node3D,
	crop_key: String,
	grid: Vector2i,
	col: int,
	row: int,
	s: float,
	growth: float,
	senescence: float,
	stress_f: float,
	grain_frac: float,
) -> void:
	## Bake all plants into a single mesh using SurfaceTool for performance.
	## Used for high-density crops (wheat, rice) where individual nodes are too slow.
	# Build one representative plant, then instance it via MultiMesh
	var sv_base: int = col * 7 + row * 13
	var sample_plant := _create_3d_plant(
		crop_key, growth, senescence, stress_f, grain_frac, sv_base
	)
	# Collect all meshes from the sample plant
	var meshes: Array[Dictionary] = []
	_collect_meshes(sample_plant, Transform3D(), meshes)
	sample_plant.free()
	if meshes.is_empty():
		return
	# For each unique mesh+material combo, create a MultiMeshInstance3D
	# Simplified: use the first mesh found for the MultiMesh
	var first: Dictionary = meshes[0]
	var base_mesh: Mesh = first["mesh"]
	var base_mat: Material = first["material"]
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = base_mesh
	var total: int = grid.x * grid.y
	mm.instance_count = total
	var i := 0
	for hi in range(grid.x):
		var u: float = (float(hi) + 0.5) / float(grid.x)
		for vi in range(grid.y):
			var v: float = (float(vi) + 0.5) / float(grid.y)
			var lx: float = (u - 0.5) * TILE_SIZE
			var lz: float = (v - 0.5) * TILE_SIZE
			var sv: int = sv_base + hi * 3 + vi * 5
			var jm: float = TILE_SIZE / float(grid.x) * 0.1
			var jx: float = (fmod(float(sv % 7), 3.0) - 1.5) * jm
			var jz: float = (fmod(float((sv * 3) % 5), 2.0) - 1.0) * jm
			# Per-plant rotation for variety
			var rot_y: float = CropRenderer3D.hash_val(sv, 0) * TAU
			var t := Transform3D()
			t = t.scaled(Vector3(s, s, s))
			t = t.rotated(Vector3.UP, rot_y)
			t.origin = Vector3(lx + jx, 0, lz + jz)
			mm.set_instance_transform(i, t)
			i += 1
	var mmi := MultiMeshInstance3D.new()
	mmi.multimesh = mm
	mmi.material_override = base_mat
	mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	container.add_child(mmi)
	# Additional mesh layers (leaves, grain) as separate MultiMeshes
	for mi in range(1, meshes.size()):
		var entry: Dictionary = meshes[mi]
		var layer_mm := MultiMesh.new()
		layer_mm.transform_format = MultiMesh.TRANSFORM_3D
		layer_mm.mesh = entry["mesh"]
		layer_mm.instance_count = total
		i = 0
		for hi in range(grid.x):
			var u: float = (float(hi) + 0.5) / float(grid.x)
			for vi in range(grid.y):
				var v: float = (float(vi) + 0.5) / float(grid.y)
				var lx: float = (u - 0.5) * TILE_SIZE
				var lz: float = (v - 0.5) * TILE_SIZE
				var sv: int = sv_base + hi * 3 + vi * 5
				var jm: float = TILE_SIZE / float(grid.x) * 0.1
				var jx: float = (fmod(float(sv % 7), 3.0) - 1.5) * jm
				var jz: float = (fmod(float((sv * 3) % 5), 2.0) - 1.0) * jm
				var rot_y: float = CropRenderer3D.hash_val(sv, 0) * TAU
				var t := Transform3D()
				t = t.scaled(Vector3(s, s, s))
				t = t.rotated(Vector3.UP, rot_y)
				t.origin = Vector3(lx + jx, 0, lz + jz)
				layer_mm.set_instance_transform(i, t)
				i += 1
		var layer_mmi := MultiMeshInstance3D.new()
		layer_mmi.multimesh = layer_mm
		layer_mmi.material_override = entry["material"]
		layer_mmi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		container.add_child(layer_mmi)


static func _collect_meshes(
	node: Node, parent_transform: Transform3D, out: Array[Dictionary]
) -> void:
	var t: Transform3D = parent_transform * node.transform if node is Node3D else parent_transform
	if node is MeshInstance3D:
		var mi: MeshInstance3D = node as MeshInstance3D
		if mi.mesh:
			out.append({"mesh": mi.mesh, "material": mi.material_override, "transform": t})
	for child in node.get_children():
		_collect_meshes(child, t, out)


static func _create_3d_plant(
	crop_key: String,
	growth: float,
	senescence: float,
	stress: float,
	grain_frac: float,
	seed_val: int,
) -> Node3D:
	match crop_key:
		"maize":
			return MaizeRenderer3D.create_plant(growth, senescence, stress, grain_frac, seed_val)
		"spring_wheat", "winter_wheat":
			return WheatRenderer3D.create_plant(growth, senescence, stress, grain_frac, seed_val)
		"sorghum":
			return SorghumRenderer3D.create_plant(growth, senescence, stress, grain_frac, seed_val)
		"rice":
			return RiceRenderer3D.create_plant(growth, senescence, stress, grain_frac, seed_val)
		"grape":
			return GrapeRenderer3D.create_plant(growth, senescence, stress, grain_frac, seed_val)
		_:
			return MaizeRenderer3D.create_plant(growth, senescence, stress, grain_frac, seed_val)


# --- API integration (same flow as 2D farm_view.gd) ---


func _ensure_game(callback: Callable) -> void:
	if not _game_id.is_empty():
		callback.call()
		return
	status_label.text = "Creating game..."
	_set_buttons_disabled(true)
	_api_client.create_game(
		func(success: bool, data: Dictionary) -> void:
			_set_buttons_disabled(false)
			if not success:
				status_label.text = "Error: could not reach backend"
				return
			_game_id = data.get("game_id", "")
			GameState.game_id = _game_id
			callback.call()
	)


func _set_buttons_disabled(disabled: bool) -> void:
	next_day_btn.disabled = disabled
	ff7_btn.disabled = disabled
	ff_all_btn.disabled = disabled
	irrigate_btn.disabled = disabled
	fertilize_btn.disabled = disabled
	plant_btn.disabled = disabled


func _on_next_day() -> void:
	_ensure_game(func() -> void: _step_days(1))


func _on_ff7() -> void:
	_ensure_game(func() -> void: _step_days(7))


func _on_ff_all() -> void:
	_ensure_game(
		func() -> void:
			_set_buttons_disabled(true)
			_api_client.start_season(_game_id, _on_season_complete)
	)


func _step_days(n: int) -> void:
	_set_buttons_disabled(true)
	_api_client.step_day(_game_id, n, _on_step_complete)


func _on_step_complete(success: bool, data: Dictionary) -> void:
	_set_buttons_disabled(false)
	if not success:
		status_label.text = "Step failed — backend error"
		return
	_last_step_data = data
	_apply_day_result(data)
	_api_client.get_forecast(_game_id, _on_forecast_received)
	# Refresh soil cutaway if open
	if _soil_view and _soil_view.is_active() and _selected_tile.x >= 0:
		_show_soil_cutaway()


func _on_forecast_received(success: bool, data: Dictionary) -> void:
	if not success:
		return
	var fc: Array = data.get("forecast", [])
	forecast_panel.update_forecast(fc)


func _apply_day_result(data: Dictionary) -> void:
	var day_num: int = data.get("day_number", 0)
	var cur_date: String = data.get("date", "")
	var w: Dictionary = data.get("weather", {})
	var balance: int = data.get("balance_credits", 0)

	date_label.text = "Day %d | %s" % [day_num, cur_date]
	credits_label.text = "%d" % balance
	var rain_mm: float = w.get("rain_mm", 0.0)
	weather_label.text = (
		"%.0f–%.0f°C  %.1fmm"
		% [
			w.get("tmin_c", 0.0),
			w.get("tmax_c", 0.0),
			rain_mm,
		]
	)
	var icon_path := "res://assets/icons/icon_sun.svg"
	if rain_mm > 5.0:
		icon_path = "res://assets/icons/icon_rain.svg"
	elif rain_mm >= 1.0:
		icon_path = "res://assets/icons/icon_cloud.svg"
	var icon_tex: Texture2D = load(icon_path)
	if icon_tex:
		weather_icon.texture = icon_tex
	# 3D rain particles + lighting
	rain.set_raining(rain_mm > 1.0, rain_mm)
	_update_weather_lighting(w)

	var patches: Dictionary = data.get("patches", {})
	_apply_patch_data(patches)


func _apply_patch_data(patches: Dictionary) -> void:
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		for patch_idx in range(patch_list.size()):
			var patch: Dictionary = patch_list[patch_idx]
			var patch_soil: String = ""
			if patch_idx < SOIL_TYPES.size():
				patch_soil = SOIL_TYPES[patch_idx]
			var stage_name: String = patch.get("crop_stage", "")
			var stage: int = _STAGE_MAP.get(stage_name, 0)
			var lai: float = patch.get("lai", 0.0)
			var crop_key: String = patch.get("crop_key", "")
			for i in range(_tile_data.size()):
				if _tile_data[i]["soil_type"] == patch_soil or patch_soil.is_empty():
					_tile_data[i]["som_total_c_g_m2"] = patch.get("som_total_c_g_m2", 0.0)
					_tile_data[i]["theta_surface"] = patch.get("soil_theta_surface", 0.0)
					_tile_data[i]["crop_key"] = crop_key
					_tile_data[i]["crop_stage"] = stage
					_tile_data[i]["lai"] = lai
					_update_tile_shader(i)
					_update_crop_visuals(i)


func _on_irrigate() -> void:
	_ensure_game(
		func() -> void:
			_api_client.execute_action(_game_id, "irrigate", {"amount_mm": 20}, _on_action_complete)
	)


func _on_fertilize() -> void:
	_ensure_game(
		func() -> void:
			(
				_api_client
				. execute_action(
					_game_id,
					"fertilize",
					{"type": "urea", "amount_kg_ha": 50},
					_on_action_complete,
				)
			)
	)


func _setup_crop_popup() -> void:
	_crop_popup = PopupMenu.new()
	for i in range(AVAILABLE_CROPS.size()):
		var crop_key: String = AVAILABLE_CROPS[i]
		_crop_popup.add_item(crop_key.capitalize(), i)
	_crop_popup.id_pressed.connect(_on_crop_selected)
	$UILayer.add_child(_crop_popup)


func _on_plant_pressed() -> void:
	if _selected_tile.x < 0:
		status_label.text = "Select a tile first to plant"
		return
	var btn_rect := plant_btn.get_global_rect()
	_crop_popup.position = Vector2i(int(btn_rect.position.x), int(btn_rect.end.y))
	_crop_popup.popup()


func _on_crop_selected(id: int) -> void:
	if id < 0 or id >= AVAILABLE_CROPS.size():
		return
	var crop_key: String = AVAILABLE_CROPS[id]
	var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
	var soil_type: String = _tile_data[idx]["soil_type"]
	var patch_idx := SOIL_TYPES.find(soil_type)
	if patch_idx < 0:
		patch_idx = 0
	_ensure_game(
		func() -> void:
			(
				_api_client
				. execute_action(
					_game_id,
					"plant",
					{"crop_key": crop_key, "patch_idx": patch_idx},
					_on_plant_complete.bind(crop_key, soil_type),
				)
			)
	)


func _on_plant_complete(
	success: bool, data: Dictionary, crop_key: String, soil_type: String
) -> void:
	if not success:
		status_label.text = "Plant failed"
		return
	var cost: int = data.get("cost_credits", 0)
	credits_label.text = "%d" % data.get("balance_credits", 0)
	for i in range(_tile_data.size()):
		if _tile_data[i]["soil_type"] == soil_type:
			_tile_data[i]["crop_key"] = crop_key
			_tile_data[i]["crop_stage"] = 1
			_tile_data[i]["lai"] = 0.0
			_update_crop_visuals(i)
	status_label.text = "Planted %s — %d credits" % [crop_key, cost]
	_step_days(1)


func _on_action_complete(success: bool, data: Dictionary) -> void:
	if not success:
		status_label.text = "Action failed"
		return
	var action: String = data.get("action", "")
	var cost: int = data.get("cost_credits", 0)
	credits_label.text = "Credits: %d" % data.get("balance_credits", 0)
	status_label.text = "%s — %d credits" % [action, cost]
	_step_days(1)


func _on_season_complete(success: bool, _data: Dictionary) -> void:
	_set_buttons_disabled(false)
	if not success:
		status_label.text = "Season failed — backend error"
		return
	status_label.text = "Season complete"


func _on_soil_view() -> void:
	if _selected_tile.x < 0:
		status_label.text = "Select a tile first to view soil"
		return
	if _last_step_data.is_empty():
		status_label.text = "Step at least 1 day to see soil data"
		return
	_show_soil_cutaway()


func _show_soil_cutaway() -> void:
	_restore_hidden_tiles()
	var col := _selected_tile.x
	var row := _selected_tile.y
	var patches: Dictionary = _last_step_data.get("patches", {})
	# Camera at +X,+Z looking toward -X,-Z.
	# Front 3 tiles (between selected and camera) must be hidden:
	var front_tiles: Array[Vector2i] = [
		Vector2i(col + 1, row),
		Vector2i(col, row + 1),
		Vector2i(col + 1, row + 1),
	]
	# Pillars: selected (center, with info+roots) + left/right neighbors.
	# Left/right = along visual row (same col+row sum, perpendicular to view).
	var pillar_tiles: Array[Vector2i] = [
		Vector2i(col, row),
		Vector2i(col - 1, row + 1),
		Vector2i(col + 1, row - 1),
	]
	# Hide front tiles + their crops
	_hidden_tiles.clear()
	for pos in front_tiles:
		if _is_valid_grid(pos):
			var idx: int = pos.y * GRID_COLS + pos.x
			_hidden_tiles.append(idx)
			_tile_meshes[idx].visible = false
			for spr in _crop_sprites[idx]:
				spr.visible = false
	# Build pillar columns
	var columns: Array[Dictionary] = []
	for i in range(pillar_tiles.size()):
		var tp := pillar_tiles[i]
		if not _is_valid_grid(tp):
			continue
		var col_data := _get_soil_column(tp, patches, i == 0)
		if not col_data.is_empty():
			columns.append(col_data)
	if columns.is_empty():
		_restore_hidden_tiles()
		status_label.text = "No soil data available"
		return
	if not _soil_view:
		_soil_view = Node3D.new()
		_soil_view.set_script(SoilView3D)
		add_child(_soil_view)
	_soil_view.show_cutaway(columns)


func _get_soil_column(tp: Vector2i, patches: Dictionary, is_center: bool) -> Dictionary:
	var idx: int = tp.y * GRID_COLS + tp.x
	var soil_type: String = _tile_data[idx]["soil_type"]
	var patch_idx := SOIL_TYPES.find(soil_type)
	if patch_idx < 0:
		patch_idx = 0
	var soil_state := {}
	var root_depth_cm := 0.0
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		if patch_idx < patch_list.size():
			var patch: Dictionary = patch_list[patch_idx]
			soil_state = patch.get("soil_state", {})
			root_depth_cm = patch.get("root_depth_cm", 0.0)
	if soil_state.is_empty():
		return {}
	return {
		"pos": _tile_meshes[idx].position,
		"soil_state": soil_state,
		"profile": SoilView3D.get_profile_layers(soil_type),
		"root_depth_cm": root_depth_cm if is_center else 0.0,
		"show_info": is_center,
	}


func _is_valid_grid(pos: Vector2i) -> bool:
	return pos.x >= 0 and pos.x < GRID_COLS and pos.y >= 0 and pos.y < GRID_ROWS


func _restore_hidden_tiles() -> void:
	for idx in _hidden_tiles:
		_tile_meshes[idx].visible = true
		_update_crop_visuals(idx)
	_hidden_tiles.clear()


func _hide_soil_cutaway() -> void:
	if _soil_view and _soil_view.is_active():
		_soil_view.hide_view()
	_restore_hidden_tiles()


func _debug_auto_start() -> void:
	_ensure_game(func() -> void: _debug_plant_crops())


func _debug_plant_crops() -> void:
	# Plant maize on sandy, wheat on organic, sorghum on clay
	_api_client.execute_action(
		_game_id,
		"plant",
		{"crop_key": "maize", "patch_idx": 0},
		func(_s: bool, _d: Dictionary) -> void:
			_api_client.execute_action(
				_game_id,
				"plant",
				{"crop_key": "spring_wheat", "patch_idx": 1},
				func(_s2: bool, _d2: Dictionary) -> void:
					_api_client.execute_action(
						_game_id,
						"plant",
						{"crop_key": "sorghum", "patch_idx": 2},
						func(_s3: bool, _d3: Dictionary) -> void: _debug_step_and_show()
					)
			)
	)


func _debug_step_and_show() -> void:
	_api_client.step_day(
		_game_id,
		7,
		func(success: bool, data: Dictionary) -> void:
			if not success:
				return
			_last_step_data = data
			_apply_day_result(data)
			_select_tile(3, 3)
			_show_soil_cutaway()
	)
