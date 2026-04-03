extends Node2D
## Isometric farm view — main game screen.
## Uses TileMapLayer for the soil grid with crop sprites,
## selection overlay, and surrounding terrain border.

enum CropStage { NONE, SEEDLING, VEGETATIVE, FLOWERING, MATURE }
enum StressState { NONE, WILTING, N_DEFICIENT }

const TILE_WIDTH := 64
const TILE_HEIGHT := 32
const GRID_COLS := 6
const GRID_ROWS := 6
const BORDER_MIN := -2
const BORDER_MAX := 7

const SOIL_TYPES: Array[String] = ["sandy", "organic", "clay"]
const TILE_TEXTURES := {
	"sandy": "res://assets/tiles/tile_sandy.svg",
	"organic": "res://assets/tiles/tile_organic.svg",
	"clay": "res://assets/tiles/tile_clay.svg",
}

## Terrain tile types and their SVG paths (source IDs 3-10)
const TERRAIN_TILES := {
	"G": "res://assets/tiles/tile_grass.svg",
	"g": "res://assets/tiles/tile_grass_dry.svg",
	"D": "res://assets/tiles/tile_dirt.svg",
	"P": "res://assets/tiles/tile_dirt_path.svg",
	"R": "res://assets/tiles/tile_rough.svg",
	"W": "res://assets/tiles/tile_water.svg",
	"Fh": "res://assets/tiles/tile_fence_h.svg",
	"Fv": "res://assets/tiles/tile_fence_v.svg",
}
const _TERRAIN_SOURCE_IDS := {
	"G": 3,
	"g": 4,
	"D": 5,
	"P": 6,
	"R": 7,
	"W": 8,
	"Fh": 9,
	"Fv": 10,
}

## 10x10 border layout (rows -2..7, cols -2..7). "." = farm tile (inner 6x6).
const BORDER_LAYOUT: Array[Array] = [
	["R", "G", "G", "G", "G", "G", "G", "G", "G", "g"],
	["G", "G", "Fv", "Fv", "Fv", "Fv", "Fv", "Fv", "G", "G"],
	["P", "Fh", ".", ".", ".", ".", ".", ".", "Fh", "G"],
	["P", "Fh", ".", ".", ".", ".", ".", ".", "Fh", "G"],
	["P", "Fh", ".", ".", ".", ".", ".", ".", "Fh", "G"],
	["P", "Fh", ".", ".", ".", ".", ".", ".", "Fh", "G"],
	["P", "Fh", ".", ".", ".", ".", ".", ".", "Fh", "G"],
	["D", "Fh", ".", ".", ".", ".", ".", ".", "Fh", "G"],
	["G", "G", "Fv", "Fv", "Fv", "Fv", "Fv", "Fv", "G", "g"],
	["G", "G", "g", "G", "G", "G", "G", "g", "W", "g"],
]

const AVAILABLE_CROPS: Array[String] = ["maize", "spring_wheat", "sorghum", "rice", "grape"]

const SoilColor = preload("res://scripts/soil_color.gd")
const CropRenderer = preload("res://scripts/crop_renderer.gd")
const MaizeRenderer = preload("res://scripts/maize_renderer.gd")
const CropPanel = preload("res://scripts/crop_panel.gd")
const SoilViewScript = preload("res://scripts/soil_view.gd")

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_data: Array[Dictionary] = []
var _crop_sprites: Array[Node2D] = []
var _soil_overlays: Array[Sprite2D] = []
var _api_client: Node
var _overlay_mode: int = SoilColor.Mode.NATURAL
var _soil_view: Node = null
var _crop_panel: Control = null
var _crop_popup: PopupMenu = null
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
@onready var plant_btn: Button = $UILayer/ActionBar/PlantButton
@onready var forecast_panel: VBoxContainer = $UILayer/ForecastPanel
@onready var status_label: Label = $UILayer/StatusLabel
@onready var camera: Camera2D = $Camera2D


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
	soil_view_btn.pressed.connect(_on_soil_view)
	plant_btn.pressed.connect(_on_plant_pressed)
	_setup_crop_popup()
	_load_selection_texture()
	selection_indicator.visible = false
	tile_layer.tile_set = _create_tile_set()
	_init_grid()
	_init_border()
	_update_camera_bounds()
	status_label.text = "F1-F3 overlays | S/M debug | Click tile for info"


func _create_tile_set() -> TileSet:
	var ts := TileSet.new()
	ts.tile_shape = TileSet.TILE_SHAPE_ISOMETRIC
	ts.tile_layout = TileSet.TILE_LAYOUT_DIAMOND_RIGHT
	ts.tile_size = Vector2i(TILE_WIDTH, TILE_HEIGHT)
	# Soil sources (IDs 0-2)
	for i in range(SOIL_TYPES.size()):
		var source := TileSetAtlasSource.new()
		source.texture = load(TILE_TEXTURES[SOIL_TYPES[i]])
		source.texture_region_size = Vector2i(TILE_WIDTH, TILE_HEIGHT)
		source.create_tile(Vector2i(0, 0))
		ts.add_source(source, i)
	# Terrain sources (IDs 3-10)
	for key: String in _TERRAIN_SOURCE_IDS:
		var source := TileSetAtlasSource.new()
		var tex: Texture2D = load(TERRAIN_TILES[key])
		if tex:
			source.texture = tex
		source.texture_region_size = Vector2i(TILE_WIDTH, TILE_HEIGHT)
		source.create_tile(Vector2i(0, 0))
		ts.add_source(source, _TERRAIN_SOURCE_IDS[key])
	return ts


func _load_selection_texture() -> void:
	var tex: Texture2D = load("res://assets/tiles/tile_selected.svg")
	if tex:
		selection_indicator.texture = tex


func _soil_source_id(soil_type: String) -> int:
	var idx := SOIL_TYPES.find(soil_type)
	if idx < 0:
		return 1
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


func _init_border() -> void:
	for layout_row in range(BORDER_LAYOUT.size()):
		var row_data: Array = BORDER_LAYOUT[layout_row]
		for layout_col in range(row_data.size()):
			var tile_key: String = row_data[layout_col]
			if tile_key == ".":
				continue
			var map_col: int = layout_col + BORDER_MIN
			var map_row: int = layout_row + BORDER_MIN
			# Fence tiles: place grass as base, overlay fence sprite
			var is_fence: bool = tile_key == "Fh" or tile_key == "Fv"
			var base_id: int = (
				_TERRAIN_SOURCE_IDS["G"] if is_fence else _TERRAIN_SOURCE_IDS.get(tile_key, 3)
			)
			tile_layer.set_cell(Vector2i(map_col, map_row), base_id, Vector2i(0, 0))
			if is_fence:
				_add_fence_sprite(tile_key, map_col, map_row)


func _add_fence_sprite(tile_key: String, map_col: int, map_row: int) -> void:
	var pos := tile_layer.position + tile_layer.map_to_local(Vector2i(map_col, map_row))
	var tex: Texture2D = load(TERRAIN_TILES[tile_key])
	# 2.5D floor shadow: light from top-right, shadow projects down-left.
	# Skew vertically (flatten) and offset to simulate isometric ground shadow.
	var shadow := Sprite2D.new()
	if tex:
		shadow.texture = tex
	shadow.position = pos + Vector2(-4.0, 3.0)
	shadow.scale = Vector2(1.0, 0.5)
	shadow.skew = -0.3
	shadow.modulate = Color(0, 0, 0, 0.18)
	shadow.z_index = 1
	add_child(shadow)
	# Fence sprite
	var fence_spr := Sprite2D.new()
	if tex:
		fence_spr.texture = tex
	fence_spr.position = pos
	fence_spr.z_index = 2
	add_child(fence_spr)


func _update_camera_bounds() -> void:
	# Center camera on the farm field — no limits, user pans freely.
	var center := tile_layer.map_to_local(Vector2i(GRID_COLS / 2, GRID_ROWS / 2))
	camera.position = tile_layer.position + center


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
	var container := Node2D.new()
	var world_pos := tile_layer.map_to_local(Vector2i(col, row))
	container.position = world_pos
	container.z_index = row + col + 1
	container.visible = false
	for ui in range(CropRenderer.PLANT_GRID):
		var u: float = CropRenderer.PLANT_FRACS[ui]
		for vi in range(CropRenderer.PLANT_GRID):
			var v: float = CropRenderer.PLANT_FRACS[vi]
			var px: float = (u - v) * TILE_WIDTH / 2.0
			var py: float = (u + v) * TILE_HEIGHT / 2.0 - TILE_HEIGHT / 2.0
			var seed_val := col * 7 + row * 13 + ui * 3 + vi * 5
			var jx: float = fmod(float(seed_val % 7), 3.0) - 1.5
			var jy: float = fmod(float((seed_val * 3) % 5), 2.0) - 1.0
			var pos := Vector2(px + jx, py + jy - 4)
			var plant := Node2D.new()
			plant.position = pos
			var stem := Sprite2D.new()
			stem.name = "stem"
			stem.scale = CropRenderer._PLANT_SCALE
			plant.add_child(stem)
			var leaves := Node2D.new()
			leaves.name = "leaves"
			plant.add_child(leaves)
			var grain := Sprite2D.new()
			grain.name = "grain"
			grain.scale = CropRenderer._PLANT_SCALE
			grain.visible = false
			plant.add_child(grain)
			container.add_child(plant)
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

	if stage == CropStage.NONE:
		container.visible = false
		return

	var lai: float = data.get("lai", 0.0)
	var grain_val: float = data.get("grain_g_m2", 0.0)
	var lai_frac: float = clampf(lai / 6.0, 0.0, 1.0)
	var grain_frac: float = clampf(grain_val / 800.0, 0.0, 1.0)

	var growth_progress: float = 0.2
	match stage:
		CropStage.SEEDLING:
			growth_progress = 0.25
		CropStage.VEGETATIVE:
			growth_progress = clampf(0.3 + lai_frac * 0.5, 0.3, 0.8)
		CropStage.FLOWERING:
			growth_progress = 0.9
		CropStage.MATURE:
			growth_progress = 1.0

	var expected_lai: float = 1.0
	match stage:
		CropStage.VEGETATIVE:
			expected_lai = 4.0
		CropStage.FLOWERING:
			expected_lai = 5.5
		CropStage.MATURE:
			expected_lai = 3.0
	var senescence: float = clampf(1.0 - lai / maxf(expected_lai, 0.1), 0.0, 1.0)
	if stage == CropStage.SEEDLING or stage == CropStage.VEGETATIVE:
		senescence = 0.0

	var stem_path := CropRenderer.crop_layer_path(crop_key, "stem")
	var grain_path := CropRenderer.crop_layer_path(crop_key, "grain")
	var has_layers: bool = CropRenderer.has_layers(crop_key)

	var stem_scale: float = growth_progress
	var stem_color := Color(0.85, 0.95, 0.8)
	stem_color = stem_color.lerp(Color(0.85, 0.78, 0.45), senescence * 0.7)

	var leaf_scale: float = clampf(lai_frac, 0.2, 1.0)
	if stage >= CropStage.FLOWERING:
		leaf_scale = maxf(leaf_scale, 0.7)
	var leaf_green := Color(0.55, 0.85, 0.35)
	var leaf_young := Color(0.7, 0.9, 0.55)
	var leaf_color := leaf_young.lerp(leaf_green, lai_frac)
	var leaf_senescent := Color(0.85, 0.75, 0.35)
	var leaf_dead := Color(0.7, 0.55, 0.3)
	leaf_color = leaf_color.lerp(leaf_senescent, senescence * 0.7)
	leaf_color = leaf_color.lerp(leaf_dead, maxf(senescence - 0.5, 0.0) * 1.5)
	if stress == StressState.WILTING:
		leaf_color = leaf_color.lerp(Color(0.6, 0.5, 0.25), 0.5)
	elif stress == StressState.N_DEFICIENT:
		leaf_color = leaf_color.lerp(Color(0.75, 0.8, 0.35), 0.4)

	var grain_visible: bool = stage >= CropStage.FLOWERING and grain_val > 1.0
	var grain_scale: float = clampf(0.3 + grain_frac * 0.7, 0.3, 1.0)
	var grain_color := Color(0.95, 0.85, 0.45).lerp(Color(0.85, 0.7, 0.3), grain_frac)

	var plant_i := 0
	for plant in container.get_children():
		if not plant is Node2D:
			continue
		if has_layers:
			var stem_spr: Sprite2D = plant.get_node_or_null("stem")
			if stem_spr:
				var tex: Texture2D = load(stem_path)
				if tex:
					stem_spr.texture = tex
				var ps := CropRenderer._PLANT_SCALE
				stem_spr.scale = Vector2(ps.x * stem_scale * 0.45, ps.y * stem_scale * 0.55)
				stem_spr.modulate = stem_color
				stem_spr.visible = true
			var leaf_node: Node2D = plant.get_node_or_null("leaves")
			if leaf_node:
				_render_crop_leaves(
					crop_key, leaf_node, senescence, stress, stem_scale, growth_progress, plant_i
				)
			var grain_spr: Sprite2D = plant.get_node_or_null("grain")
			if grain_spr:
				var tex: Texture2D = load(grain_path)
				if tex:
					grain_spr.texture = tex
				grain_spr.scale = CropRenderer._PLANT_SCALE * grain_scale * 0.65
				grain_spr.modulate = grain_color
				grain_spr.visible = grain_visible
				var ph := (plant_i * 2654435761) & 0x7FFFFFFF
				var ear_x: float = (float(ph % 100) / 100.0 - 0.5) * 3.0
				var ear_y: float = (float((ph * 3) % 100) / 100.0 - 0.5) * 2.0
				grain_spr.position = Vector2(ear_x, ear_y - 2.0)
		else:
			var suffix: String = CropRenderer.STAGE_SUFFIX.get(stage, "")
			if suffix.is_empty():
				continue
			var path := CropRenderer.crop_sprite_path(crop_key, suffix)
			var tex: Texture2D = load(path)
			var stem_spr: Sprite2D = plant.get_node_or_null("stem")
			if stem_spr and tex:
				stem_spr.texture = tex
				stem_spr.scale = CropRenderer._PLANT_SCALE * clampf(0.3 + lai_frac * 0.7, 0.3, 1.0)
				stem_spr.modulate = leaf_color
				stem_spr.visible = true
		plant_i += 1
	container.visible = true


func _render_crop_leaves(
	crop_key: String,
	leaf_node: Node2D,
	senescence: float,
	stress: int,
	stem_height_frac: float,
	growth_progress: float = 0.0,
	plant_seed: int = 0,
) -> void:
	match crop_key:
		"maize":
			MaizeRenderer.draw_leaves(
				leaf_node, senescence, stress, stem_height_frac, growth_progress, plant_seed
			)
		_:
			MaizeRenderer.draw_leaves(
				leaf_node, senescence, stress, stem_height_frac, growth_progress, plant_seed
			)


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
	var name: String = SoilColor.MODE_NAMES.get(mode, "Unknown")
	status_label.text = "Overlay: %s (F1 natural, F2 SOM, F3 moisture)" % name


func _cycle_debug_som(idx: int) -> void:
	var current: float = _tile_data[idx].get("som_total_c_g_m2", 0.0)
	var next_val := SoilColor.DEBUG_SOM_PRESETS[0]
	for preset: float in SoilColor.DEBUG_SOM_PRESETS:
		if preset > current + 1.0:
			next_val = preset
			break
	_tile_data[idx]["som_total_c_g_m2"] = next_val
	_update_tile_color(idx)
	_refresh_status_label(idx)


func _cycle_debug_moisture(idx: int) -> void:
	var current: float = _tile_data[idx].get("theta_surface", 0.0)
	var next_val := SoilColor.DEBUG_MOISTURE_PRESETS[0]
	for preset: float in SoilColor.DEBUG_MOISTURE_PRESETS:
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
		if not _last_step_data.is_empty():
			_show_soil_cutaway(col, row)
			_show_crop_panel(data)


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
	plant_btn.disabled = disabled


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
	if _soil_view and _soil_view.is_active() and _selected_tile.x >= 0:
		_show_soil_cutaway(_selected_tile.x, _selected_tile.y)
		var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
		_show_crop_panel(_tile_data[idx])


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
	var icon_path := "res://assets/icons/icon_sun.svg"
	if rain > 5.0:
		icon_path = "res://assets/icons/icon_rain.svg"
	elif rain >= 1.0:
		icon_path = "res://assets/icons/icon_cloud.svg"
	var icon_tex: Texture2D = load(icon_path)
	if icon_tex:
		weather_icon.texture = icon_tex
	weather.set_raining(rain > 2.0)

	var patches: Dictionary = data.get("patches", {})
	_apply_patch_day_results(patches)
	_update_all_tile_colors()

	if season_done:
		_show_harvest_report()


func _apply_patch_day_results(patches: Dictionary) -> void:
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		for patch_idx in range(patch_list.size()):
			var patch: Dictionary = patch_list[patch_idx]
			var patch_soil: String = ""
			if patch_idx < SOIL_TYPES.size():
				patch_soil = SOIL_TYPES[patch_idx]
			var stage_name: String = patch.get("crop_stage", "")
			var stage: int = CropRenderer.STAGE_MAP.get(stage_name, CropStage.NONE)
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


func _setup_crop_popup() -> void:
	_crop_popup = PopupMenu.new()
	for i in range(AVAILABLE_CROPS.size()):
		var crop_key: String = AVAILABLE_CROPS[i]
		var icon_path := CropRenderer.crop_sprite_path(crop_key, "seedling")
		var tex: Texture2D = load(icon_path) if ResourceLoader.exists(icon_path) else null
		if tex:
			_crop_popup.add_icon_item(tex, crop_key.capitalize(), i)
		else:
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
			_tile_data[i]["crop_stage"] = CropStage.SEEDLING
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
	status_label.text = "%s — %d credits, advancing day..." % [action, cost]
	_step_days(1)


func _on_soil_view() -> void:
	if _selected_tile.x < 0:
		status_label.text = "Select a tile first to view soil"
		return
	_show_soil_cutaway(_selected_tile.x, _selected_tile.y)


func _show_soil_cutaway(col: int, row: int) -> void:
	if _last_step_data.is_empty():
		status_label.text = "Step at least 1 day to see soil data"
		return

	_restore_hidden_tiles()

	var sel := Vector2i(col, row)
	var col_left := Vector2i(col - 1, row - 1)
	var col_right := Vector2i(col + 1, row + 1)
	var inv_tiles: Array[Vector2i] = [
		Vector2i(col - 1, row),
		Vector2i(col, row + 1),
		Vector2i(col - 1, row + 1),
	]

	_hidden_tiles.clear()
	for inv in inv_tiles:
		if _is_valid_farm_tile(inv):
			_hidden_tiles.append(inv)
			tile_layer.erase_cell(inv)
			var inv_idx := inv.y * GRID_COLS + inv.x
			_crop_sprites[inv_idx].visible = false
			if inv_idx < _soil_overlays.size():
				_soil_overlays[inv_idx].visible = false

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
	var profile_layers := SoilViewScript.get_profile_layers(soil_type)

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
		if _is_valid_farm_tile(side):
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
						"profile": SoilViewScript.get_profile_layers(side_soil),
						"root_depth_cm": 0.0,
						"show_info": false,
					}
				)
			)

	if not _soil_view:
		var scene: PackedScene = load("res://scenes/soil_view.tscn")
		_soil_view = scene.instantiate()
		_soil_view.z_index = -1
		add_child(_soil_view)
		move_child(_soil_view, 0)
		_soil_view.connect("closed", _on_soil_view_closed)
	var offset := tile_layer.position
	for c: Dictionary in columns:
		c["pos"] = c["pos"] + offset
	_soil_view.show_columns(columns)


func _is_valid_farm_tile(pos: Vector2i) -> bool:
	return pos.x >= 0 and pos.x < GRID_COLS and pos.y >= 0 and pos.y < GRID_ROWS


func _restore_hidden_tiles() -> void:
	for inv in _hidden_tiles:
		if _is_valid_farm_tile(inv):
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
	_hide_crop_panel()


func _show_crop_panel(data: Dictionary) -> void:
	_hide_crop_panel()
	var panel: PanelContainer = CropPanel.create(data)
	if not panel:
		return
	panel.position = Vector2(get_viewport().get_visible_rect().size.x - 200, 70)
	panel.size = Vector2(180, 0)
	$UILayer.add_child(panel)
	_crop_panel = panel


func _hide_crop_panel() -> void:
	if _crop_panel:
		_crop_panel.queue_free()
		_crop_panel = null


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
	var ui_layer: CanvasLayer = $UILayer
	ui_layer.add_child(report)
	report.load_report(_game_id)
	report.connect("closed", _on_report_closed)


func _on_report_closed() -> void:
	for i in range(_tile_data.size()):
		_tile_data[i]["crop_stage"] = CropStage.NONE
		_tile_data[i]["stress"] = StressState.NONE
		_tile_data[i]["grain_g_m2"] = 0.0
		_update_crop_visuals(i)
	_set_buttons_disabled(false)
	status_label.text = "New season — ready to step"


func _apply_season_results(field_results: Dictionary) -> void:
	for field_key: String in field_results:
		var patches: Array = field_results[field_key]
		for patch_idx in range(patches.size()):
			var patch: Dictionary = patches[patch_idx]
			var grain: float = patch.get("grain_g_m2", 0.0)
			var soil: Dictionary = patch.get("soil_state", {})
			var som_c: float = soil.get("som_total_c_g_m2", 0.0) if soil else 0.0
			var theta: float = soil.get("theta_surface", 0.0) if soil else 0.0
			var patch_soil: String = ""
			if patch_idx < SOIL_TYPES.size():
				patch_soil = SOIL_TYPES[patch_idx]
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
