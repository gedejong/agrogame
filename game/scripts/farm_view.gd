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

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_data: Array[Dictionary] = []
var _crop_sprites: Array[Sprite2D] = []
var _soil_overlays: Array[Sprite2D] = []
var _api_client: Node
var _season_running := false

@onready var tile_layer: TileMapLayer = $TileLayer
@onready var soil_overlay_layer: Node2D = $SoilOverlayLayer
@onready var crop_layer: Node2D = $CropLayer
@onready var selection_indicator: Sprite2D = $SelectionIndicator
@onready var weather: Node = $UILayer/WeatherOverlay
@onready var ui_panel: Control = $UILayer/UIPanel
@onready var status_label: Label = $UILayer/UIPanel/StatusLabel
@onready var season_button: Button = $UILayer/UIPanel/SeasonButton
@onready var camera: Camera2D = $Camera2D


func _ready() -> void:
	_api_client = preload("res://scripts/api_client.gd").new()
	add_child(_api_client)
	season_button.pressed.connect(_on_season_pressed)
	_load_selection_texture()
	selection_indicator.visible = false
	tile_layer.tile_set = _create_tile_set()
	_init_grid()
	status_label.text = ("Click tile to select. 1-4 crop stage, W wilt, N deficient, 0 clear.")


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


func _create_soil_overlay(col: int, row: int, soil_type: String) -> void:
	var sprite := Sprite2D.new()
	var tex_path: String = TILE_TEXTURES.get(soil_type, TILE_TEXTURES["organic"])
	var tex: Texture2D = load(tex_path)
	if tex:
		sprite.texture = tex
	sprite.position = tile_layer.map_to_local(Vector2i(col, row))
	sprite.z_index = 0
	sprite.modulate = Color.WHITE
	sprite.visible = false
	soil_overlay_layer.add_child(sprite)
	_soil_overlays.append(sprite)


func _update_tile_color(idx: int) -> void:
	if idx < 0 or idx >= _soil_overlays.size():
		return
	var data: Dictionary = _tile_data[idx]
	var som_c: float = data.get("som_total_c_g_m2", 0.0)
	var theta: float = data.get("theta_surface", 0.0)
	if som_c <= 0.0 and theta <= 0.0:
		_soil_overlays[idx].visible = false
		return
	var color := SoilColor.calculate(som_c, theta)
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
	if _selected_tile.x < 0:
		return
	var col := _selected_tile.x
	var row := _selected_tile.y
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


func _on_season_pressed() -> void:
	if _season_running:
		return
	if _game_id.is_empty():
		_create_game_then_run()
	else:
		_run_season()


func _create_game_then_run() -> void:
	status_label.text = "Creating game..."
	season_button.disabled = true
	_api_client.create_game(_on_game_created)


func _on_game_created(success: bool, data: Dictionary) -> void:
	if not success:
		status_label.text = "Error: could not reach backend"
		season_button.disabled = false
		return
	_game_id = data.get("game_id", "")
	_run_season()


func _run_season() -> void:
	_season_running = true
	status_label.text = "Running season..."
	season_button.disabled = true
	weather.set_raining(true)
	_api_client.start_season(_game_id, _on_season_complete)


func _on_season_complete(success: bool, data: Dictionary) -> void:
	_season_running = false
	season_button.disabled = false
	weather.set_raining(false)
	if not success:
		status_label.text = "Season failed — backend error"
		return
	var total_days: int = data.get("total_days", 0)
	var field_results: Dictionary = data.get("field_results", {})
	_apply_season_results(field_results)
	var total_grain := _total_grain_g_m2()
	status_label.text = ("Season complete: %d days, yield %.0f g/m²" % [total_days, total_grain])


func _apply_season_results(field_results: Dictionary) -> void:
	## Parse per-patch results from API response: grain, soil state, tile colors.
	var patch_idx := 0
	var last_soil := {}
	for field_key: String in field_results:
		var patches: Array = field_results[field_key]
		for patch: Dictionary in patches:
			if patch_idx < _tile_data.size():
				var grain: float = patch.get("grain_g_m2", 0.0)
				_tile_data[patch_idx]["grain_g_m2"] = grain
				_tile_data[patch_idx]["crop_stage"] = CropStage.MATURE
				_update_crop_visuals(patch_idx)
				var soil: Dictionary = patch.get("soil_state", {})
				if not soil.is_empty():
					last_soil = soil
					_tile_data[patch_idx]["som_total_c_g_m2"] = soil.get("som_total_c_g_m2", 0.0)
					_tile_data[patch_idx]["theta_surface"] = soil.get("theta_surface", 0.0)
			patch_idx += 1
	# Propagate last soil state to remaining tiles
	for i in range(patch_idx, _tile_data.size()):
		_tile_data[i]["crop_stage"] = CropStage.MATURE
		_update_crop_visuals(i)
		if not last_soil.is_empty():
			_tile_data[i]["som_total_c_g_m2"] = last_soil.get("som_total_c_g_m2", 0.0)
			_tile_data[i]["theta_surface"] = last_soil.get("theta_surface", 0.0)
	_update_all_tile_colors()


func _total_grain_g_m2() -> float:
	var total := 0.0
	for tile: Dictionary in _tile_data:
		total += tile.get("grain_g_m2", 0.0)
	return total
