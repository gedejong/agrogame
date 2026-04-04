extends Node3D
## 3D farm view — Phase 2 of 2D→3D migration (ADR-007).
## Renders 6x6 tile grid as MeshInstance3D with soil PBR shader.
## Crop billboard sprites (Sprite3D) per tile.
## Raycast click detection, SOM/moisture shader updates from API.

const GRID_COLS := 6
const GRID_ROWS := 6
const TILE_SIZE := 1.0
const TILE_HEIGHT := 0.1

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

const CropBillboard = preload("res://scripts/crop_billboard.gd")
const CropRenderer = preload("res://scripts/crop_renderer.gd")
const SoilView3D = preload("res://scripts/soil_view_3d.gd")

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
var _api_client: Node
var _last_step_data: Dictionary = {}

@onready var camera_rig: Node3D = $CameraRig
@onready var camera: Camera3D = $CameraRig/Camera3D
@onready var tile_root: Node3D = $TileRoot
@onready var crop_root: Node3D = $CropRoot
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


func _build_tile_grid() -> void:
	var shader: Shader = load("res://shaders/soil_tile.gdshader")
	var box := PlaneMesh.new()
	box.size = Vector2(TILE_SIZE * 0.995, TILE_SIZE * 0.995)
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
			# Crop billboard sprites (16 per tile) — separate from tile mesh
			# to avoid depth buffer conflicts with parent MeshInstance3D.
			var crop_container := Node3D.new()
			crop_container.position = mesh_inst.position
			crop_root.add_child(crop_container)
			var sprites := CropBillboard.create_plants(TILE_SIZE, col, row)
			for spr: Sprite3D in sprites:
				crop_container.add_child(spr)
			_crop_sprites.append(sprites)
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


func _update_crop_visuals(idx: int) -> void:
	var data: Dictionary = _tile_data[idx]
	var crop_key: String = data.get("crop_key", "")
	var stage: int = data.get("crop_stage", 0)
	var lai: float = data.get("lai", 0.0)
	var stress: int = data.get("stress", 0)
	var sprites: Array = _crop_sprites[idx]
	for spr: Sprite3D in sprites:
		CropBillboard.update_sprite(spr, crop_key, stage, lai, stress)


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
	var rain: float = w.get("rain_mm", 0.0)
	weather_label.text = (
		"%.0f–%.0f°C  %.1fmm"
		% [
			w.get("tmin_c", 0.0),
			w.get("tmax_c", 0.0),
			rain,
		]
	)
	var icon_path := "res://assets/icons/icon_sun.svg"
	if rain > 5.0:
		icon_path = "res://assets/icons/icon_rain.svg"
	elif rain >= 1.0:
		icon_path = "res://assets/icons/icon_cloud.svg"
	var icon_tex: Texture2D = load(icon_path)
	if icon_tex:
		weather_icon.texture = icon_tex

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
	var col := _selected_tile.x
	var row := _selected_tile.y
	var idx := row * GRID_COLS + col
	var soil_type: String = _tile_data[idx]["soil_type"]
	var patch_idx := SOIL_TYPES.find(soil_type)
	if patch_idx < 0:
		patch_idx = 0
	var patches: Dictionary = _last_step_data.get("patches", {})
	var soil_state := {}
	var root_depth_cm := 0.0
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		if patch_idx < patch_list.size():
			var patch: Dictionary = patch_list[patch_idx]
			soil_state = patch.get("soil_state", {})
			root_depth_cm = patch.get("root_depth_cm", 0.0)
	if soil_state.is_empty():
		status_label.text = "No soil data available"
		return
	var profile := SoilView3D.get_profile_layers(soil_type)
	var tile_pos: Vector3 = _tile_meshes[idx].position
	if not _soil_view:
		_soil_view = Node3D.new()
		_soil_view.set_script(SoilView3D)
		add_child(_soil_view)
	_soil_view.show(tile_pos, soil_state, profile, root_depth_cm)


func _hide_soil_cutaway() -> void:
	if _soil_view and _soil_view.is_active():
		_soil_view.hide_view()
