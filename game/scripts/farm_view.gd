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
const CROP_TEXTURES := {
	CropStage.SEEDLING: "res://assets/crops/maize_seedling.svg",
	CropStage.VEGETATIVE: "res://assets/crops/maize_vegetative.svg",
	CropStage.FLOWERING: "res://assets/crops/maize_flowering.svg",
	CropStage.MATURE: "res://assets/crops/maize_mature.svg",
}

## Stress overlay textures
const STRESS_TEXTURES := {
	StressState.WILTING: "res://assets/crops/maize_wilting.svg",
	StressState.N_DEFICIENT: "res://assets/crops/maize_ndeficient.svg",
}

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
const _MODE_NAMES := {
	SoilColor.Mode.NATURAL: "Natural",
	SoilColor.Mode.SOM_HEATMAP: "SOM Heatmap",
	SoilColor.Mode.MOISTURE_HEATMAP: "Moisture Heatmap",
}

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_data: Array[Dictionary] = []
var _crop_sprites: Array[Sprite2D] = []
var _soil_overlays: Array[Sprite2D] = []
var _api_client: Node
var _season_running := false
var _overlay_mode: int = SoilColor.Mode.NATURAL

@onready var tile_layer: TileMapLayer = $TileLayer
@onready var soil_overlay_layer: Node2D = $SoilOverlayLayer
@onready var crop_layer: Node2D = $CropLayer
@onready var selection_indicator: Sprite2D = $SelectionIndicator
@onready var weather: Node = $UILayer/WeatherOverlay
@onready var date_label: Label = $UILayer/TopBar/DateLabel
@onready var credits_label: Label = $UILayer/TopBar/CreditsLabel
@onready var weather_label: Label = $UILayer/TopBar/WeatherLabel
@onready var next_day_btn: Button = $UILayer/ActionBar/NextDayButton
@onready var ff7_btn: Button = $UILayer/ActionBar/FastForward7
@onready var ff_all_btn: Button = $UILayer/ActionBar/FastForwardAll
@onready var irrigate_btn: Button = $UILayer/ActionBar/IrrigateButton
@onready var fertilize_btn: Button = $UILayer/ActionBar/FertilizeButton
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
						"crop_stage": CropStage.NONE,
						"stress": StressState.NONE,
						"grain_g_m2": 0.0,
						"som_total_c_g_m2": 0.0,
						"theta_surface": 0.0,
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


func _create_crop_sprite(col: int, row: int) -> void:
	var sprite := Sprite2D.new()
	var world_pos := tile_layer.map_to_local(Vector2i(col, row))
	sprite.position = world_pos + Vector2(0, -8)
	sprite.z_index = row + col + 1
	sprite.visible = false
	crop_layer.add_child(sprite)
	_crop_sprites.append(sprite)


func _update_crop_visuals(idx: int) -> void:
	if idx < 0 or idx >= _crop_sprites.size():
		return
	var data: Dictionary = _tile_data[idx]
	var stage: int = data["crop_stage"]
	var stress: int = data["stress"]
	var sprite: Sprite2D = _crop_sprites[idx]
	if stress != StressState.NONE and STRESS_TEXTURES.has(stress):
		var tex: Texture2D = load(STRESS_TEXTURES[stress])
		if tex:
			sprite.texture = tex
			sprite.visible = true
		return
	if stage == CropStage.NONE:
		sprite.visible = false
		return
	if CROP_TEXTURES.has(stage):
		var tex: Texture2D = load(CROP_TEXTURES[stage])
		if tex:
			sprite.texture = tex
			sprite.visible = true


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
		var som_c: float = data.get("som_total_c_g_m2", 0.0)
		var theta: float = data.get("theta_surface", 0.0)
		status_label.text = (
			"[%d,%d] %s | SOM %.0f gC/m² | θ %.2f" % [col, row, data["soil_type"], som_c, theta]
		)


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
	_apply_day_result(data)
	_api_client.get_forecast(_game_id, _on_forecast_received)


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
	credits_label.text = "Credits: %d" % balance
	var rain: float = w.get("rain_mm", 0.0)
	weather_label.text = (
		"%.0f–%.0f°C  Rain: %.1fmm" % [w.get("tmin_c", 0.0), w.get("tmax_c", 0.0), rain]
	)
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
			# Map API phenology stage to CropStage
			var stage_name: String = patch.get("crop_stage", "")
			var stage: int = _STAGE_MAP.get(stage_name, CropStage.NONE)
			for i in range(_tile_data.size()):
				if _tile_data[i]["soil_type"] == patch_soil or patch_soil.is_empty():
					_tile_data[i]["grain_g_m2"] = patch.get("grain_g_m2", 0.0)
					_tile_data[i]["som_total_c_g_m2"] = patch.get("som_total_c_g_m2", 0.0)
					_tile_data[i]["theta_surface"] = patch.get("soil_theta_surface", 0.0)
					_tile_data[i]["crop_stage"] = stage
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
