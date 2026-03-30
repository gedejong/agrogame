extends Node2D
## Isometric farm view — main game screen (AGRO-114).
## Displays patches as isometric tiles, crop growth sprites, and handles
## tile selection, season execution, and weather overlay.

## Crop growth stage enum
enum CropStage { NONE, SEEDLING, VEGETATIVE, FLOWERING, MATURE }

## Stress state enum
enum StressState { NONE, WILTING, N_DEFICIENT }

const TILE_WIDTH := 64
const TILE_HEIGHT := 32
const GRID_COLS := 6
const GRID_ROWS := 4

## Tile texture paths by soil type
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

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_data: Array[Dictionary] = []
var _tile_sprites: Array[Sprite2D] = []
var _crop_sprites: Array[Sprite2D] = []
var _api_client: Node
var _season_running := false

@onready var tile_map: Node2D = $TileLayer
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
	_init_grid()
	status_label.text = ("Click tile to select. 1-4 crop stage, W wilt, N deficient, 0 clear.")


func _load_selection_texture() -> void:
	var tex: Texture2D = load("res://assets/tiles/tile_selected.svg")
	if tex:
		selection_indicator.texture = tex


func _init_grid() -> void:
	_tile_data.clear()
	_tile_sprites.clear()
	_crop_sprites.clear()
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
					}
				)
			)
			_create_tile_sprite(col, row, soil_type)
			_create_crop_sprite(col, row)


func _create_tile_sprite(col: int, row: int, soil_type: String) -> void:
	var sprite := Sprite2D.new()
	var tex_path: String = TILE_TEXTURES.get(soil_type, TILE_TEXTURES["organic"])
	var tex: Texture2D = load(tex_path)
	if tex:
		sprite.texture = tex
	sprite.position = _tile_to_world(col, row)
	sprite.z_index = row + col
	tile_map.add_child(sprite)
	_tile_sprites.append(sprite)


func _create_crop_sprite(col: int, row: int) -> void:
	var sprite := Sprite2D.new()
	sprite.position = _tile_to_world(col, row) + Vector2(0, -8)
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
			_handle_tile_click(mb.position)
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


func _handle_tile_click(_screen_pos: Vector2) -> void:
	var world_pos := get_global_mouse_position()
	var col := _world_to_tile_col(world_pos)
	var row := _world_to_tile_row(world_pos)
	if col >= 0 and col < GRID_COLS and row >= 0 and row < GRID_ROWS:
		_selected_tile = Vector2i(col, row)
		_update_selection_indicator()
		var idx := row * GRID_COLS + col
		var data: Dictionary = _tile_data[idx]
		status_label.text = (
			"Selected: [%d,%d] soil=%s crop=%d" % [col, row, data["soil_type"], data["crop_stage"]]
		)


func _update_selection_indicator() -> void:
	if _selected_tile.x < 0:
		selection_indicator.visible = false
		return
	selection_indicator.visible = true
	selection_indicator.position = _tile_to_world(_selected_tile.x, _selected_tile.y)
	# Render above all tiles and crops
	selection_indicator.z_index = GRID_COLS + GRID_ROWS + 10


func _tile_to_world(col: int, row: int) -> Vector2:
	var x := (col - row) * TILE_WIDTH / 2.0
	var y := (col + row) * TILE_HEIGHT / 2.0
	return Vector2(x + 300, y + 100)


func _world_to_tile_col(world_pos: Vector2) -> int:
	var adjusted := world_pos - Vector2(300, 100)
	var col_f := adjusted.x / TILE_WIDTH + adjusted.y / TILE_HEIGHT
	return int(round(col_f))


func _world_to_tile_row(world_pos: Vector2) -> int:
	var adjusted := world_pos - Vector2(300, 100)
	var row_f := adjusted.y / TILE_HEIGHT - adjusted.x / TILE_WIDTH
	return int(round(row_f))


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
	status_label.text = "Season complete: %d days, yield %.0f g/m²" % [total_days, total_grain]


func _apply_season_results(field_results: Dictionary) -> void:
	## Parse per-patch grain_g_m2 from API response and update tile data.
	var patch_idx := 0
	for field_key: String in field_results:
		var patches: Array = field_results[field_key]
		for patch: Dictionary in patches:
			if patch_idx < _tile_data.size():
				var grain: float = patch.get("grain_g_m2", 0.0)
				_tile_data[patch_idx]["grain_g_m2"] = grain
				_tile_data[patch_idx]["crop_stage"] = CropStage.MATURE
				_update_crop_visuals(patch_idx)
			patch_idx += 1
	# If API returned fewer patches than tiles, mark remaining as mature
	for i in range(patch_idx, _tile_data.size()):
		_tile_data[i]["crop_stage"] = CropStage.MATURE
		_update_crop_visuals(i)


func _total_grain_g_m2() -> float:
	var total := 0.0
	for tile: Dictionary in _tile_data:
		total += tile.get("grain_g_m2", 0.0)
	return total
