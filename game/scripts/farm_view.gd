extends Node2D
## Isometric farm view — main game screen.
## Uses TileMapLayer for the soil grid (AGRO-118), with crop sprites
## and selection overlay on separate Node2D layers.

## Crop growth stage enum
enum CropStage { NONE, SEEDLING, VEGETATIVE, FLOWERING, MATURE }

## Stress state enum
enum StressState { NONE, WILTING, N_DEFICIENT }

const TILE_WIDTH := 64
const TILE_HEIGHT := 32
const GRID_COLS := 6
const GRID_ROWS := 6

## Soil types and their tile textures (order = TileSet source ID)
const SOIL_TYPES: Array[String] = ["sandy", "organic", "clay"]
const TILE_TEXTURES := {
	"sandy": "res://assets/tiles/tile_sandy.svg",
	"organic": "res://assets/tiles/tile_organic.svg",
	"clay": "res://assets/tiles/tile_clay.svg",
}

## Crop sprite paths by stage
## Stage enum to sprite suffix mapping
const _STAGE_SUFFIX := {
	CropStage.SEEDLING: "seedling",
	CropStage.VEGETATIVE: "vegetative",
	CropStage.FLOWERING: "flowering",
	CropStage.MATURE: "mature",
}
const _STRESS_SUFFIX := {
	StressState.WILTING: "wilting",
	StressState.N_DEFICIENT: "ndeficient",
}
## Crop key prefix mapping (spring_wheat/winter_wheat → wheat sprites)
const _CROP_PREFIX := {
	"spring_wheat": "wheat",
	"winter_wheat": "wheat",
}
const _FALLBACK_CROP := "maize"

const SoilColor = preload("res://scripts/soil_color.gd")
const _SOM_PRESETS: Array[float] = [0.0, 500.0, 2000.0, 4000.0]
const _MOISTURE_PRESETS: Array[float] = [0.0, 0.05, 0.20, 0.40]
const _STAGE_MAP := {
	"planted": CropStage.SEEDLING,
	"emerged": CropStage.SEEDLING,
	"vegetative": CropStage.VEGETATIVE,
	"flowering": CropStage.FLOWERING,
	"grain_fill": CropStage.MATURE,
	"maturity": CropStage.MATURE,
}
## 4x4 grid of plants across the tile in isometric coordinates.
## Tile diamond: top (0,-HH), right (HW,0), bottom (0,HH), left (-HW,0).
## Grid positions at 1/8, 3/8, 5/8, 7/8 in both tile axes.
const _PLANT_SCALE := Vector2(0.45, 0.45)
const _PLANT_GRID := 4
const _PLANT_FRACS: Array[float] = [0.125, 0.375, 0.625, 0.875]
const _MODE_NAMES := {
	SoilColor.Mode.NATURAL: "Natural",
	SoilColor.Mode.SOM_HEATMAP: "SOM Heatmap",
	SoilColor.Mode.MOISTURE_HEATMAP: "Moisture Heatmap",
}

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_data: Array[Dictionary] = []
var _crop_sprites: Array[Node2D] = []
var _soil_overlays: Array[Sprite2D] = []
var _api_client: Node
var _season_running := false
var _overlay_mode: int = SoilColor.Mode.NATURAL
var _soil_view: Node = null
var _last_step_data: Dictionary = {}
var _hidden_tiles: Array[Vector2i] = []

@onready var tile_layer: TileMapLayer = $TileLayer
@onready var soil_overlay_layer: Node2D = $SoilOverlayLayer
@onready var crop_layer: Node2D = $CropLayer
@onready var selection_indicator: Sprite2D = $SelectionIndicator
@onready var weather: Node = $UILayer/WeatherOverlay
@onready var date_label: Label = $UILayer/TopBar/DateLabel
@onready var credits_label: Label = $UILayer/TopBar/CreditsLabel
@onready var weather_label: Label = $UILayer/TopBar/WeatherLabel
@onready var weather_icon: TextureRect = $UILayer/TopBar/WeatherIcon
@onready var next_day_btn: Button = $UILayer/ActionBar/NextDayButton
@onready var ff7_btn: Button = $UILayer/ActionBar/FastForward7
@onready var ff_all_btn: Button = $UILayer/ActionBar/FastForwardAll
@onready var irrigate_btn: Button = $UILayer/ActionBar/IrrigateButton
@onready var fertilize_btn: Button = $UILayer/ActionBar/FertilizeButton
@onready var soil_view_btn: Button = $UILayer/ActionBar/SoilViewButton
@onready var forecast_panel: VBoxContainer = $UILayer/ForecastPanel
@onready var status_label: Label = $UILayer/StatusLabel
@onready var camera: Camera2D = $Camera2D


func _ready() -> void:
	_api_client = preload("res://scripts/api_client.gd").new()
	add_child(_api_client)
	# Restore game_id from global state (persists across scene changes)
	if GameState.game_id != "":
		_game_id = GameState.game_id
	next_day_btn.pressed.connect(_on_next_day)
	ff7_btn.pressed.connect(_on_ff7)
	ff_all_btn.pressed.connect(_on_ff_all)
	irrigate_btn.pressed.connect(_on_irrigate)
	fertilize_btn.pressed.connect(_on_fertilize)
	soil_view_btn.pressed.connect(_on_soil_view)
	_load_selection_texture()
	selection_indicator.visible = false
	tile_layer.tile_set = _create_tile_set()
	_init_grid()
	status_label.text = "F1-F3 overlays | S/M debug | Click tile for info"


func _create_tile_set() -> TileSet:
	var ts := TileSet.new()
	ts.tile_shape = TileSet.TILE_SHAPE_ISOMETRIC
	ts.tile_layout = TileSet.TILE_LAYOUT_DIAMOND_RIGHT
	ts.tile_size = Vector2i(TILE_WIDTH, TILE_HEIGHT)
	for i in range(SOIL_TYPES.size()):
		var source := TileSetAtlasSource.new()
		source.texture = load(TILE_TEXTURES[SOIL_TYPES[i]])
		source.texture_region_size = Vector2i(TILE_WIDTH, TILE_HEIGHT)
		source.create_tile(Vector2i(0, 0))
		ts.add_source(source, i)
	return ts


func _load_selection_texture() -> void:
	var tex: Texture2D = load("res://assets/tiles/tile_selected.svg")
	if tex:
		selection_indicator.texture = tex


func _soil_source_id(soil_type: String) -> int:
	var idx := SOIL_TYPES.find(soil_type)
	if idx < 0:
		return 1  # default to organic
	return idx


func _init_grid() -> void:
	_tile_data.clear()
	_crop_sprites.clear()
	_soil_overlays.clear()
	for row in range(GRID_ROWS):
		for col in range(GRID_COLS):
			var soil_type := "organic"
			if col < 2:
				soil_type = "sandy"
			elif col >= 4:
				soil_type = "clay"
			(
				_tile_data
				. append(
					{
						"col": col,
						"row": row,
						"soil_type": soil_type,
						"crop_key": "maize",
						"crop_stage_name": "",
						"crop_stage": CropStage.NONE,
						"root_depth_cm": 0.0,
						"stress": StressState.NONE,
						"grain_g_m2": 0.0,
						"som_total_c_g_m2": 0.0,
						"theta_surface": 0.0,
						"lai": 0.0,
					}
				)
			)
			tile_layer.set_cell(Vector2i(col, row), _soil_source_id(soil_type), Vector2i(0, 0))
			_create_soil_overlay(col, row, soil_type)
			_create_crop_sprite(col, row)


func _create_soil_overlay(col: int, _row: int, _soil_type: String) -> void:
	var sprite := Sprite2D.new()
	var tex: Texture2D = load("res://assets/tiles/tile_white.svg")
	if tex:
		sprite.texture = tex
	sprite.position = tile_layer.map_to_local(Vector2i(col, _row))
	sprite.z_index = 0
	sprite.modulate = Color(1, 1, 1, 0)
	sprite.visible = false
	soil_overlay_layer.add_child(sprite)
	_soil_overlays.append(sprite)


func _update_tile_color(idx: int) -> void:
	if idx < 0 or idx >= _soil_overlays.size():
		return
	var data: Dictionary = _tile_data[idx]
	var som_c: float = data.get("som_total_c_g_m2", 0.0)
	var theta: float = data.get("theta_surface", 0.0)
	if som_c <= 0.0 and theta <= 0.0 and _overlay_mode == SoilColor.Mode.NATURAL:
		_soil_overlays[idx].visible = false
		return
	var color := SoilColor.calculate(som_c, theta, _overlay_mode)
	# Heatmap modes: fully opaque overlay replaces base tile visually.
	# Natural mode: semi-transparent overlay darkens base tile.
	if _overlay_mode != SoilColor.Mode.NATURAL:
		color.a = 0.85
	else:
		color.a = 0.6
	_soil_overlays[idx].modulate = color
	_soil_overlays[idx].visible = true


func _update_all_tile_colors() -> void:
	for i in range(_tile_data.size()):
		_update_tile_color(i)


static func _crop_sprite_path(crop_key: String, suffix: String) -> String:
	var prefix: String = _CROP_PREFIX.get(crop_key, crop_key)
	var path := "res://assets/crops/%s_%s.svg" % [prefix, suffix]
	if ResourceLoader.exists(path):
		return path
	# Fallback to maize
	return "res://assets/crops/%s_%s.svg" % [_FALLBACK_CROP, suffix]


func _create_crop_sprite(col: int, row: int) -> void:
	var container := Node2D.new()
	var world_pos := tile_layer.map_to_local(Vector2i(col, row))
	container.position = world_pos
	container.z_index = row + col + 1
	container.visible = false
	# 4x4 grid mapped to isometric tile coordinates.
	# u,v in [0,1] map to screen via: x = (u-v)*HW, y = (u+v)*HH - HH
	for ui in range(_PLANT_GRID):
		var u: float = _PLANT_FRACS[ui]
		for vi in range(_PLANT_GRID):
			var v: float = _PLANT_FRACS[vi]
			var px: float = (u - v) * TILE_WIDTH / 2.0
			var py: float = (u + v) * TILE_HEIGHT / 2.0 - TILE_HEIGHT / 2.0
			# Deterministic jitter per plant
			var seed_val := col * 7 + row * 13 + ui * 3 + vi * 5
			var jx: float = fmod(float(seed_val % 7), 3.0) - 1.5
			var jy: float = fmod(float((seed_val * 3) % 5), 2.0) - 1.0
			var sprite := Sprite2D.new()
			sprite.position = Vector2(px + jx, py + jy - 4)
			sprite.scale = _PLANT_SCALE
			container.add_child(sprite)
	crop_layer.add_child(container)
	_crop_sprites.append(container)


func _update_crop_visuals(idx: int) -> void:
	if idx < 0 or idx >= _crop_sprites.size():
		return
	var data: Dictionary = _tile_data[idx]
	var stage: int = data["crop_stage"]
	var stress: int = data["stress"]
	var container: Node2D = _crop_sprites[idx]

	var crop_key: String = data.get("crop_key", "maize")
	var tex: Texture2D = null
	if stress != StressState.NONE and _STRESS_SUFFIX.has(stress):
		var path := _crop_sprite_path(crop_key, _STRESS_SUFFIX[stress])
		tex = load(path)
	elif stage != CropStage.NONE and _STAGE_SUFFIX.has(stage):
		var path := _crop_sprite_path(crop_key, _STAGE_SUFFIX[stage])
		tex = load(path)

	if tex:
		# Scale sprites based on LAI (0 = tiny, ~6 = full size for maize)
		var lai: float = data.get("lai", 0.0)
		var growth_scale: float = clampf(0.3 + lai * 0.12, 0.3, 1.0)
		var final_scale := _PLANT_SCALE * growth_scale
		for child in container.get_children():
			if child is Sprite2D:
				child.texture = tex
				child.scale = final_scale
		container.visible = true
	else:
		container.visible = false


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			_handle_tile_click()
	elif event is InputEventKey:
		var ke := event as InputEventKey
		if ke.pressed:
			_handle_key(ke.keycode)


func _handle_key(keycode: int) -> void:
	# Overlay toggles work without tile selection
	match keycode:
		KEY_F1:
			_set_overlay_mode(SoilColor.Mode.NATURAL)
			return
		KEY_F2:
			_set_overlay_mode(SoilColor.Mode.SOM_HEATMAP)
			return
		KEY_F3:
			_set_overlay_mode(SoilColor.Mode.MOISTURE_HEATMAP)
			return
		KEY_ESCAPE:
			_hide_soil_cutaway()
			return
	# Tile-specific keys require selection
	if _selected_tile.x < 0:
		return
	var col := _selected_tile.x
	var row := _selected_tile.y
	var idx := row * GRID_COLS + col
	match keycode:
		KEY_1:
			set_crop_stage(col, row, CropStage.SEEDLING)
		KEY_2:
			set_crop_stage(col, row, CropStage.VEGETATIVE)
		KEY_3:
			set_crop_stage(col, row, CropStage.FLOWERING)
		KEY_4:
			set_crop_stage(col, row, CropStage.MATURE)
		KEY_0:
			set_crop_stage(col, row, CropStage.NONE)
			set_stress_state(col, row, StressState.NONE)
		KEY_W:
			set_stress_state(col, row, StressState.WILTING)
		KEY_N:
			set_stress_state(col, row, StressState.N_DEFICIENT)
		KEY_S:
			_cycle_debug_som(idx)
		KEY_M:
			_cycle_debug_moisture(idx)


func _set_overlay_mode(mode: int) -> void:
	_overlay_mode = mode
	_update_all_tile_colors()
	var name: String = _MODE_NAMES.get(mode, "Unknown")
	status_label.text = "Overlay: %s (F1 natural, F2 SOM, F3 moisture)" % name


func _cycle_debug_som(idx: int) -> void:
	var current: float = _tile_data[idx].get("som_total_c_g_m2", 0.0)
	var next_val := _SOM_PRESETS[0]
	for preset: float in _SOM_PRESETS:
		if preset > current + 1.0:
			next_val = preset
			break
	_tile_data[idx]["som_total_c_g_m2"] = next_val
	_update_tile_color(idx)
	_refresh_status_label(idx)


func _cycle_debug_moisture(idx: int) -> void:
	var current: float = _tile_data[idx].get("theta_surface", 0.0)
	var next_val := _MOISTURE_PRESETS[0]
	for preset: float in _MOISTURE_PRESETS:
		if preset > current + 0.001:
			next_val = preset
			break
	_tile_data[idx]["theta_surface"] = next_val
	_update_tile_color(idx)
	_refresh_status_label(idx)


func _refresh_status_label(idx: int) -> void:
	var data: Dictionary = _tile_data[idx]
	var som_c: float = data.get("som_total_c_g_m2", 0.0)
	var theta: float = data.get("theta_surface", 0.0)
	var col: int = data["col"]
	var row: int = data["row"]
	status_label.text = (
		"[%d,%d] %s | SOM %.0f gC/m² | θ %.2f" % [col, row, data["soil_type"], som_c, theta]
	)


func _handle_tile_click() -> void:
	var world_pos := get_global_mouse_position()
	var local_pos := tile_layer.to_local(world_pos)
	var map_pos := tile_layer.local_to_map(local_pos)
	var col := map_pos.x
	var row := map_pos.y
	if col >= 0 and col < GRID_COLS and row >= 0 and row < GRID_ROWS:
		_selected_tile = Vector2i(col, row)
		_update_selection_indicator()
		var idx := row * GRID_COLS + col
		var data: Dictionary = _tile_data[idx]
		var crop_key: String = data.get("crop_key", "")
		var stage_name: String = data.get("crop_stage_name", "")
		var lai: float = data.get("lai", 0.0)
		var root_cm: float = data.get("root_depth_cm", 0.0)
		var som_c: float = data.get("som_total_c_g_m2", 0.0)
		var theta: float = data.get("theta_surface", 0.0)
		status_label.text = (
			"%s %s | LAI %.1f | Root %.0fcm | SOM %.0f | θ %.2f"
			% [crop_key, stage_name, lai, root_cm, som_c, theta]
		)
		# Show inline soil cutaway below the selected tile
		if not _last_step_data.is_empty():
			_show_soil_cutaway(col, row)


func _update_selection_indicator() -> void:
	if _selected_tile.x < 0:
		selection_indicator.visible = false
		return
	selection_indicator.visible = true
	var local_pos := tile_layer.map_to_local(_selected_tile)
	selection_indicator.position = tile_layer.position + local_pos
	selection_indicator.z_index = GRID_COLS + GRID_ROWS + 10


func get_selected_tile() -> Vector2i:
	return _selected_tile


func get_tile_data(col: int, row: int) -> Dictionary:
	if col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS:
		return {}
	return _tile_data[row * GRID_COLS + col]


func set_crop_stage(col: int, row: int, stage: int) -> void:
	if col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS:
		return
	var idx := row * GRID_COLS + col
	_tile_data[idx]["crop_stage"] = stage
	_update_crop_visuals(idx)


func set_stress_state(col: int, row: int, stress: int) -> void:
	if col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS:
		return
	var idx := row * GRID_COLS + col
	_tile_data[idx]["stress"] = stress
	_update_crop_visuals(idx)


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


func _on_next_day() -> void:
	_ensure_game(func() -> void: _step_days(1))


func _on_ff7() -> void:
	_ensure_game(func() -> void: _step_days(7))


func _on_ff_all() -> void:
	_ensure_game(
		func() -> void:
			_set_buttons_disabled(true)
			weather.set_raining(true)
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
	# Refresh soil cutaway if it's showing
	if _soil_view and _soil_view.is_active() and _selected_tile.x >= 0:
		_show_soil_cutaway(_selected_tile.x, _selected_tile.y)


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
	var season_done: bool = data.get("season_complete", false)

	date_label.text = "Day %d | %s" % [day_num, cur_date]
	credits_label.text = "%d" % balance
	var rain: float = w.get("rain_mm", 0.0)
	weather_label.text = (
		"%.0f–%.0f°C  %.1fmm" % [w.get("tmin_c", 0.0), w.get("tmax_c", 0.0), rain]
	)
	# Update weather icon
	var icon_path := "res://assets/icons/icon_sun.svg"
	if rain > 5.0:
		icon_path = "res://assets/icons/icon_rain.svg"
	elif rain >= 1.0:
		icon_path = "res://assets/icons/icon_cloud.svg"
	var icon_tex: Texture2D = load(icon_path)
	if icon_tex:
		weather_icon.texture = icon_tex
	weather.set_raining(rain > 2.0)

	# Update per-patch tile data from step result
	var patches: Dictionary = data.get("patches", {})
	_apply_patch_day_results(patches)
	_update_all_tile_colors()

	if season_done:
		_show_harvest_report()


func _apply_patch_day_results(patches: Dictionary) -> void:
	## Map per-patch day results to tiles by soil type, update crop visuals.
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		for patch_idx in range(patch_list.size()):
			var patch: Dictionary = patch_list[patch_idx]
			var patch_soil: String = ""
			if patch_idx < SOIL_TYPES.size():
				patch_soil = SOIL_TYPES[patch_idx]
			var stage_name: String = patch.get("crop_stage", "")
			var stage: int = _STAGE_MAP.get(stage_name, CropStage.NONE)
			var lai: float = patch.get("lai", 0.0)
			var root_cm: float = patch.get("root_depth_cm", 0.0)
			var crop_key: String = patch.get("crop_key", "maize")
			for i in range(_tile_data.size()):
				if _tile_data[i]["soil_type"] == patch_soil or patch_soil.is_empty():
					_tile_data[i]["grain_g_m2"] = patch.get("grain_g_m2", 0.0)
					_tile_data[i]["som_total_c_g_m2"] = patch.get("som_total_c_g_m2", 0.0)
					_tile_data[i]["theta_surface"] = patch.get("soil_theta_surface", 0.0)
					_tile_data[i]["crop_stage"] = stage
					_tile_data[i]["crop_stage_name"] = stage_name
					_tile_data[i]["lai"] = lai
					_tile_data[i]["root_depth_cm"] = root_cm
					_tile_data[i]["crop_key"] = crop_key
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


func _on_soil_view() -> void:
	if _selected_tile.x < 0:
		status_label.text = "Select a tile first to view soil"
		return
	_show_soil_cutaway(_selected_tile.x, _selected_tile.y)


func _show_soil_cutaway(col: int, row: int) -> void:
	if _last_step_data.is_empty():
		status_label.text = "Step at least 1 day to see soil data"
		return

	# Restore previously hidden tiles
	_restore_hidden_tiles()

	# DIAMOND_RIGHT isometric layout neighbor mapping:
	# (col,row) screen pos follows: x = (col+row)*32, y = (row-col)*16 + offset
	# Col-left: (col-1, row-1)  Col-right: (col+1, row+1) — same visual row
	# Inv (front 3, toward viewer): (col-1, row), (col, row+1), (col-1, row+1)
	var sel := Vector2i(col, row)
	var col_left := Vector2i(col - 1, row - 1)
	var col_right := Vector2i(col + 1, row + 1)
	var inv_tiles: Array[Vector2i] = [
		Vector2i(col - 1, row),
		Vector2i(col, row + 1),
		Vector2i(col - 1, row + 1),
	]

	# Hide front tiles (make invisible) + their crops
	_hidden_tiles.clear()
	for inv in inv_tiles:
		if _is_valid_tile(inv):
			_hidden_tiles.append(inv)
			tile_layer.erase_cell(inv)
			var inv_idx := inv.y * GRID_COLS + inv.x
			_crop_sprites[inv_idx].visible = false
			if inv_idx < _soil_overlays.size():
				_soil_overlays[inv_idx].visible = false

	# Get soil state for the selected tile
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
		_restore_hidden_tiles()
		status_label.text = "Step at least 1 day to see soil data"
		return
	var profile_layers := _get_profile_layers(soil_type)

	# Build column positions: sel (with info) + left/right (visual only)
	var columns: Array[Dictionary] = []
	(
		columns
		. append(
			{
				"pos": tile_layer.map_to_local(sel),
				"soil_state": soil_state,
				"profile": profile_layers,
				"root_depth_cm": root_depth_cm,
				"show_info": true,
			}
		)
	)
	for side in [col_left, col_right]:
		if _is_valid_tile(side):
			var side_idx: int = side.y * GRID_COLS + side.x
			var side_soil: String = _tile_data[side_idx]["soil_type"]
			var side_patch := SOIL_TYPES.find(side_soil)
			if side_patch < 0:
				side_patch = 0
			var side_state := {}
			for fk: String in patches:
				var pl: Array = patches[fk]
				if side_patch < pl.size():
					side_state = pl[side_patch].get("soil_state", {})
			(
				columns
				. append(
					{
						"pos": tile_layer.map_to_local(side),
						"soil_state": side_state if side_state else soil_state,
						"profile": _get_profile_layers(side_soil),
						"root_depth_cm": 0.0,
						"show_info": false,
					}
				)
			)

	if not _soil_view:
		var scene: PackedScene = load("res://scenes/soil_view.tscn")
		_soil_view = scene.instantiate()
		_soil_view.z_index = -1
		# Add behind tiles — hidden front tiles create the viewing window
		add_child(_soil_view)
		move_child(_soil_view, 0)
		_soil_view.connect("closed", _on_soil_view_closed)
	# Offset column positions by tile_layer position (columns are in tile-local space)
	var offset := tile_layer.position
	for c: Dictionary in columns:
		c["pos"] = c["pos"] + offset
	_soil_view.show_columns(columns)


func _is_valid_tile(pos: Vector2i) -> bool:
	return pos.x >= 0 and pos.x < GRID_COLS and pos.y >= 0 and pos.y < GRID_ROWS


func _restore_hidden_tiles() -> void:
	for inv in _hidden_tiles:
		if _is_valid_tile(inv):
			var inv_idx := inv.y * GRID_COLS + inv.x
			var soil_type: String = _tile_data[inv_idx]["soil_type"]
			tile_layer.set_cell(inv, _soil_source_id(soil_type), Vector2i(0, 0))
			_update_crop_visuals(inv_idx)
			_update_tile_color(inv_idx)
	_hidden_tiles.clear()


func _on_soil_view_closed() -> void:
	_restore_hidden_tiles()


func _hide_soil_cutaway() -> void:
	if _soil_view and _soil_view.is_active():
		_soil_view.hide_view()
	_restore_hidden_tiles()


func _get_profile_layers(soil_type: String) -> Array:
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


func _on_action_complete(success: bool, data: Dictionary) -> void:
	if not success:
		status_label.text = "Action failed"
		return
	var action: String = data.get("action", "")
	var cost: int = data.get("cost_credits", 0)
	credits_label.text = "Credits: %d" % data.get("balance_credits", 0)
	status_label.text = "%s — %d credits, advancing day..." % [action, cost]
	# Auto-step 1 day so the player sees the effect immediately
	_step_days(1)


func _on_season_complete(success: bool, data: Dictionary) -> void:
	_set_buttons_disabled(false)
	weather.set_raining(false)
	if not success:
		status_label.text = "Season failed — backend error"
		return
	var field_results: Dictionary = data.get("field_results", {})
	_apply_season_results(field_results)
	_show_harvest_report()


func _show_harvest_report() -> void:
	_set_buttons_disabled(true)
	var report_scene: PackedScene = load("res://scenes/harvest_report.tscn")
	var report: Control = report_scene.instantiate()
	# Add as overlay on the UILayer so farm view stays visible behind it
	var ui_layer: CanvasLayer = $UILayer
	ui_layer.add_child(report)
	report.load_report(_game_id)
	report.connect("closed", _on_report_closed)


func _on_report_closed() -> void:
	# Reset all tile crop visuals for the new season
	for i in range(_tile_data.size()):
		_tile_data[i]["crop_stage"] = CropStage.NONE
		_tile_data[i]["stress"] = StressState.NONE
		_tile_data[i]["grain_g_m2"] = 0.0
		_update_crop_visuals(i)
	_set_buttons_disabled(false)
	status_label.text = "New season — ready to step"


func _apply_season_results(field_results: Dictionary) -> void:
	## Map each patch result to tiles sharing its soil type.
	## Patch order matches SOIL_TYPES: 0=sandy, 1=organic, 2=clay.
	for field_key: String in field_results:
		var patches: Array = field_results[field_key]
		for patch_idx in range(patches.size()):
			var patch: Dictionary = patches[patch_idx]
			var grain: float = patch.get("grain_g_m2", 0.0)
			var soil: Dictionary = patch.get("soil_state", {})
			var som_c: float = soil.get("som_total_c_g_m2", 0.0) if soil else 0.0
			var theta: float = soil.get("theta_surface", 0.0) if soil else 0.0
			# Find soil type for this patch index
			var patch_soil: String = ""
			if patch_idx < SOIL_TYPES.size():
				patch_soil = SOIL_TYPES[patch_idx]
			# Apply to all tiles matching this soil type
			for i in range(_tile_data.size()):
				if _tile_data[i]["soil_type"] == patch_soil or patch_soil.is_empty():
					_tile_data[i]["grain_g_m2"] = grain
					_tile_data[i]["crop_stage"] = CropStage.MATURE
					_tile_data[i]["som_total_c_g_m2"] = som_c
					_tile_data[i]["theta_surface"] = theta
					_update_crop_visuals(i)
	_update_all_tile_colors()


func _total_grain_g_m2() -> float:
	var total := 0.0
	for tile: Dictionary in _tile_data:
		total += tile.get("grain_g_m2", 0.0)
	return total
