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

## Soil type colors for tile tinting
const SOIL_COLORS := {
	"sandy": Color(0.83, 0.72, 0.59),
	"loam": Color(0.55, 0.45, 0.33),
	"clay": Color(0.36, 0.25, 0.20),
}

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_data: Array[Dictionary] = []
var _api_client: Node
var _season_running := false

@onready var tile_map: Node2D = $TileLayer
@onready var crop_layer: Node2D = $CropLayer
@onready var selection_indicator: Sprite2D = $SelectionIndicator
@onready var weather: Node = $WeatherOverlay
@onready var ui_panel: Control = $UIPanel
@onready var status_label: Label = $UIPanel/StatusLabel
@onready var season_button: Button = $UIPanel/SeasonButton
@onready var camera: Camera2D = $Camera2D


func _ready() -> void:
	_api_client = preload("res://scripts/api_client.gd").new()
	add_child(_api_client)
	season_button.pressed.connect(_on_season_pressed)
	selection_indicator.visible = false
	_init_grid()
	status_label.text = "Click a tile to select. Press 'Run Season' to simulate."


func _init_grid() -> void:
	_tile_data.clear()
	for row in range(GRID_ROWS):
		for col in range(GRID_COLS):
			var soil_type := "loam"
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


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			_handle_tile_click(mb.position)


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


func _tile_to_world(col: int, row: int) -> Vector2:
	var x := (col - row) * TILE_WIDTH / 2.0
	var y := (col + row) * TILE_HEIGHT / 2.0
	return Vector2(x + 300, y + 100)


func _world_to_tile_col(world_pos: Vector2) -> int:
	var adjusted := world_pos - Vector2(300, 100)
	var col_f := adjusted.x / TILE_WIDTH + adjusted.y / TILE_HEIGHT
	return int(floor(col_f))


func _world_to_tile_row(world_pos: Vector2) -> int:
	var adjusted := world_pos - Vector2(300, 100)
	var row_f := adjusted.y / TILE_HEIGHT - adjusted.x / TILE_WIDTH
	return int(floor(row_f))


func get_selected_tile() -> Vector2i:
	return _selected_tile


func get_tile_data(col: int, row: int) -> Dictionary:
	if col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS:
		return {}
	return _tile_data[row * GRID_COLS + col]


func set_crop_stage(col: int, row: int, stage: int) -> void:
	if col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS:
		return
	_tile_data[row * GRID_COLS + col]["crop_stage"] = stage


func set_stress_state(col: int, row: int, stress: int) -> void:
	if col < 0 or col >= GRID_COLS or row < 0 or row >= GRID_ROWS:
		return
	_tile_data[row * GRID_COLS + col]["stress"] = stress


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
	status_label.text = "Season complete: %d days" % total_days
	# Update all tiles to mature/harvested state
	for i in range(_tile_data.size()):
		_tile_data[i]["crop_stage"] = CropStage.MATURE
