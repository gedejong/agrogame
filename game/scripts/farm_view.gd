extends Node3D
## 3D farm view — Phase 2 of 2D→3D migration (ADR-007).
## Renders 6x6 tile grid as MeshInstance3D with soil PBR shader.
## Crop billboard sprites (Sprite3D) per tile.
## Raycast click detection, SOM/moisture shader updates from API.

const CropRenderer3D = preload("res://scripts/crop_renderer_3d.gd")

const GRID_COLS := 6
const GRID_ROWS := 6
const TILE_SIZE := 1.0
const TILE_HEIGHT := 0.1
## How many real-world meters one tile represents.
## Crop heights and soil depths are divided by this to get world units.
const METERS_PER_TILE := 2.0

## Wind: mapped from weather API wind_m_s. Calm=0.05, gale=1.0.
## Ref: Beaufort scale — 0-2 m/s calm, 2-5 breeze, 5-10 strong, >10 gale.
const WIND_SCALE_MAX_MS := 8.0
const WIND_MIN_STRENGTH := 0.05

const LOAD_RETRY_MAX_S := 30.0  # the longest wait between layout-load retries (#564)
const SOM_MAX_C_G_M2 := 5000.0
const THETA_SATURATED := 0.45
const AVAILABLE_CROPS: Array[String] = ["maize", "spring_wheat", "sorghum", "rice", "grape"]
## Plants per tile as (rows across, plants per row). A tile is
## METERS_PER_TILE^2 = 4 m^2, so plants/tile / 4 = plants/m^2.
## Maize 5x8 = 40/tile = 10 plants/m^2 — realistic grain-maize population
## (~75-100k plants/ha); broad-leaf geometry closes the canopy at this density.
const CROP_GRID := {
	"maize": Vector2i(5, 8),
	"spring_wheat": Vector2i(10, 40),
	"winter_wheat": Vector2i(10, 40),
	"sorghum": Vector2i(3, 10),
	"rice": Vector2i(10, 8),
	"grape": Vector2i(2, 2),
}

var _game_id: String = ""
var _selected_tile := Vector2i(-1, -1)
var _tile_meshes: Array[MeshInstance3D] = []
var _tile_data: Array[Dictionary] = []
var _tile_materials: Array[ShaderMaterial] = []
var _crop_sprites: Array[Array] = []
var _crop_popup: CropPopup = null
var _fertilizer_popup: PopupMenu = null
var _lime_popup: LimePopup = null
var _cutaway := SoilCutawayController.new()
var _quick_status: QuickStatusCard = null
var _previews: ActionPreviews = null
var _stress_icons: StressIcons = null
var _api_client: Node
var _last_step_data: Dictionary = {}
## Last known credit balance, used to grey out unaffordable fertilizer tiers.
## -1 means "not yet known" (before the first cost preview) → nothing disabled.
var _balance_credits: int = -1
var _wind_strength: float = 0.15
var _wind_ms: float = 2.0
var _wind_dir: Vector2 = Vector2(0.7, 0.7)
var _debug_console: DebugConsole = null
var _debug := FarmViewDebug.new()
## Per-patch history: keyed by FarmLayout.patch_key, each an Array[Dictionary].
## Capped at FarmViewHistory.MAX_HISTORY_DAYS. Cleared on season reset.
var _daily_history: Dictionary = {}
var _layout: Array = []  # every field, [{field_id, patches}], as laid out (#516, #600)
## Scene changer and title-return delay, swappable so tests can observe them.
var _change_scene: Callable
var _title_delay_s: float = 2.0
## Set by _set_buttons_disabled(true) while a request holds the bar (load, create,
## a /step, or an /action and the step its reply triggers), and cleared only by
## the reply that releases it, so nothing landing meanwhile re-enables a button (#534).
var _bar_held: bool = false
var _releases: int = 0  # times the bar was released; see _on_reconciled (#564)
var _load_failures: int = 0  # failed layout loads in a row (#564)
var _load_retry_s: float = 1.0  # the first layout-load retry's delay; doubles per failure

@onready var camera_rig: Node3D = $CameraRig
@onready var camera: Camera3D = $CameraRig/Camera3D
@onready var tile_root: Node3D = $TileRoot
@onready var crop_root: Node3D = $CropRoot
@onready var rain: GPUParticles3D = $Rain
@onready var fog_clouds: GPUParticles3D = $FogClouds
@onready var sun: DirectionalLight3D = $DirectionalLight3D
@onready var env: WorldEnvironment = $WorldEnvironment
@onready var status_label: Label = $UILayer/StatusLabel
@onready var date_label: Label = $UILayer/BottomBar/BottomVBox/TopBar/DateLabel
@onready var credits_label: Label = $UILayer/BottomBar/BottomVBox/TopBar/CreditsLabel
@onready var weather_label: Label = $UILayer/BottomBar/BottomVBox/TopBar/WeatherLabel
@onready var weather_icon: TextureRect = $UILayer/BottomBar/BottomVBox/TopBar/WeatherIcon
@onready var next_day_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/NextDayButton
@onready var ff7_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/FastForward7
@onready var ff_all_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/FastForwardAll
@onready var irrigate_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/IrrigateButton
@onready var fertilize_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/FertilizeButton
@onready var tillage_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/TillageButton
@onready var lime_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/LimeButton
@onready var plant_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/PlantButton
@onready var harvest_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/HarvestButton
@onready var soil_view_btn: Button = $UILayer/BottomBar/BottomVBox/ActionBar/SoilViewButton
@onready var forecast_panel: VBoxContainer = $UILayer/ForecastPanel


func _ready() -> void:
	if _api_client == null:  # tests inject a stub before _ready
		_api_client = preload("res://scripts/api_client.gd").new()
		add_child(_api_client)
	_change_scene = get_tree().change_scene_to_file
	# Keep the handed-over game (#516); _ensure_game covers debug tools and tests.
	_game_id = GameState.game_id
	next_day_btn.pressed.connect(_on_next_day)
	ff7_btn.pressed.connect(_on_ff7)
	ff_all_btn.pressed.connect(_on_ff_all)
	irrigate_btn.pressed.connect(_on_irrigate)
	fertilize_btn.pressed.connect(_on_fertilize)
	tillage_btn.pressed.connect(_on_tillage)
	lime_btn.pressed.connect(_on_lime)
	plant_btn.pressed.connect(_on_plant_pressed)
	harvest_btn.pressed.connect(_on_harvest_pressed)
	soil_view_btn.pressed.connect(_on_soil_view)
	_previews = ActionPreviews.new(
		_api_client,
		{
			"irrigate": irrigate_btn,
			"fertilize": fertilize_btn,
			"tillage": tillage_btn,
			"lime": lime_btn,
		},
		func(balance: int) -> void: _balance_credits = balance,
		func() -> bool: return _bar_held,
	)
	_setup_crop_popup()
	_setup_fertilizer_popup()
	_setup_lime_popup()
	_apply_ui_theme()
	_build_tile_grid()
	_apply_layout(ScenarioCatalog.default_fields())
	_stress_icons = StressIcons.new()
	add_child(_stress_icons)
	# Debug console: toggle with backtick (`)
	_debug_console = DebugConsole.new()
	_debug_console.position = Vector2(10, 80)
	_debug_console.size = Vector2(250, 0)
	_debug_console.wind_changed.connect(_on_debug_wind)
	_debug_console.rain_changed.connect(_on_debug_rain)
	var debug_layer := CanvasLayer.new()
	debug_layer.layer = 100  # always on top
	add_child(debug_layer)
	debug_layer.add_child(_debug_console)
	status_label.text = "3D view \u2014 click tile to select"
	if not _game_id.is_empty():
		_load_layout()
	var debug_auto: bool = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	if debug_auto:
		_start_debug_driver()


func _apply_ui_theme() -> void:
	var bottom_bar: PanelContainer = $UILayer/BottomBar
	bottom_bar.add_theme_stylebox_override("panel", UiTheme.create_hud_style(true))
	UiTheme.add_blur_bg(bottom_bar, UiTheme.BAR_BG)
	var info_bar: HBoxContainer = $UILayer/BottomBar/BottomVBox/TopBar
	UiTheme.style_label(date_label, "header")
	UiTheme.style_label(credits_label, "header")
	UiTheme.style_label(weather_label, "body")
	for icon_name: String in ["DateIcon", "CreditsIcon", "WeatherIcon"]:
		info_bar.get_node(icon_name).modulate = UiTheme.ICON_TINT
	UiTheme.replace_spacers(info_bar, ["Spacer1", "Spacer2"])
	weather_icon.mouse_filter = Control.MOUSE_FILTER_STOP
	weather_icon.gui_input.connect(_on_weather_clicked)
	weather_label.mouse_filter = Control.MOUSE_FILTER_STOP
	weather_label.gui_input.connect(_on_weather_clicked)
	var action_bar: HBoxContainer = $UILayer/BottomBar/BottomVBox/ActionBar
	for child: Node in action_bar.get_children():
		if child is Button:
			UiTheme.style_button(child)
		elif child is VSeparator:
			UiTheme.style_vseparator(child)
	UiTheme.add_divider($UILayer/BottomBar/BottomVBox, 1)
	UiTheme.style_label(status_label, "muted")
	forecast_panel.visible = false


func _build_tile_grid() -> void:
	## Tile nodes and per-tile data, built by FarmTiles (#546).
	var dims := Vector2i(GRID_COLS, GRID_ROWS)
	var grid := FarmTiles.build_grid(tile_root, crop_root, dims, TILE_SIZE)
	_tile_meshes.append_array(grid["meshes"])
	_tile_materials.append_array(grid["materials"])
	_crop_sprites.append_array(grid["crop_sprites"])
	_tile_data.append_array(grid["tile_data"])


func _apply_layout(fields: Array) -> void:
	## Lay every field out as a row band of its patches' column bands, textured
	## by soil (#516), with FarmLayout.FIELD_GAP between fields (#600).
	_layout = fields
	FarmLayout.assign_fields(fields, _tile_data, _tile_materials, Vector2i(GRID_COLS, GRID_ROWS))
	var row_z := FarmLayout.row_z(fields.size(), GRID_ROWS, TILE_SIZE)
	for i in range(_tile_data.size()):
		_tile_meshes[i].position.z = row_z[_tile_data[i]["row"]]
		(_crop_sprites[i][0] as Node3D).position = _tile_meshes[i].position


func _load_layout() -> void:
	## Actions wait for the layout, so none targets the placeholder bands.
	_set_buttons_disabled(true)
	_api_client.get_game(_game_id, _on_game_loaded)


func _on_game_loaded(success: bool, data: Dictionary) -> void:
	var fields: Array = FarmLayout.fields_from_game(data)
	var unfit := FarmLayout.layout_error(fields, Vector2i(GRID_COLS, GRID_ROWS))
	if data.get("not_found", false):
		# Backend lost the game (e.g. restarted): never substitute a default (#516).
		status_label.text = "Game not found, returning to title"
		_game_id = ""
		GameState.game_id = ""
		var title := "res://scenes/main.tscn"
		get_tree().create_timer(_title_delay_s).timeout.connect(_change_scene.bind(title))
	elif not success or fields.is_empty():
		# The bar stays held (#516), so retry on our own, backing off (#564).
		var delay: float = minf(_load_retry_s * pow(2.0, _load_failures), LOAD_RETRY_MAX_S)
		_load_failures += 1
		status_label.text = "Error: could not load game %s, retrying in %.0f s" % [_game_id, delay]
		get_tree().create_timer(delay).timeout.connect(_load_layout)
	elif not unfit.is_empty():
		# Showing part of the farm would hide a field, so the bar stays held (#600).
		status_label.text = "Error: game %s does not fit the map: %s" % [_game_id, unfit]
	else:
		if _load_failures > 0:  # replace the retry notice
			status_label.text = "Game %s loaded" % _game_id
		_load_failures = 0
		_apply_layout(fields)
		_show_balance(data.get("balance_credits", -1))
		_set_buttons_disabled(false)


## The loaded game's balance, in place of the scene's "—" (#582); -1 when unknown.
func _show_balance(balance: int) -> void:
	if balance < 0:
		return
	_balance_credits = balance
	credits_label.text = "%d" % balance


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb := event as InputEventMouseButton
		if mb.pressed and mb.button_index == MOUSE_BUTTON_LEFT:
			_handle_click(mb.position)
	elif event is InputEventKey:
		var ke := event as InputEventKey
		if ke.pressed and ke.keycode == KEY_ESCAPE:
			_cutaway.hide_cutaway(_tile_meshes, _crop_sprites, _update_crop_visuals)
			_deselect()
		elif ke.pressed and ke.keycode == KEY_QUOTELEFT:
			_debug_console.toggle()


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
	var soil_type: String = data.get("soil_type", "")
	# Show Quick Status card instead of full sparkline panel
	_show_quick_status(data, soil_type)
	_update_harvest_button()


func _deselect() -> void:
	if _selected_tile.x >= 0:
		var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
		_tile_materials[idx].set_shader_parameter("selected", 0.0)
	_selected_tile = Vector2i(-1, -1)
	_hide_quick_status()
	_cutaway.hide_tile_info()
	_update_harvest_button()


func _show_quick_status(tile_data: Dictionary, soil_type: String) -> void:
	_hide_quick_status()
	_quick_status = QuickStatusCard.new()
	_quick_status.position = Vector2(16, 40)
	_quick_status.size = Vector2(180, 0)
	_quick_status.show_status(tile_data, soil_type)
	_quick_status.history_requested.connect(_on_quick_status_history)
	_quick_status.soil_view_requested.connect(_on_soil_view)
	$UILayer.add_child(_quick_status)


## Rebuild the card from the selected tile's current data, so it never outlives a
## crop or status change from a step, action reply or reconcile (#582).
func _refresh_quick_status() -> void:
	if _selected_tile.x < 0:
		return
	var data: Dictionary = _tile_data[_selected_tile.y * GRID_COLS + _selected_tile.x]
	_show_quick_status(data, data.get("soil_type", ""))


func _hide_quick_status() -> void:
	if _quick_status:
		_quick_status.queue_free()
		_quick_status = null


func _on_quick_status_history() -> void:
	if _selected_tile.x < 0:
		return
	var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
	var data: Dictionary = _tile_data[idx]
	var history: Array = _daily_history.get(FarmLayout.tile_key(data), [])
	_cutaway.show_tile_info(data.get("soil_type", ""), data.get("crop_key", ""), history, $UILayer)


func _update_tile_shader(idx: int) -> void:
	var data: Dictionary = _tile_data[idx]
	var som_frac: float = clampf(data.get("som_total_c_g_m2", 0.0) / SOM_MAX_C_G_M2, 0.0, 1.0)
	var moisture_frac: float = clampf(data.get("theta_surface", 0.0) / THETA_SATURATED, 0.0, 1.0)
	_tile_materials[idx].set_shader_parameter("som_frac", som_frac)
	_tile_materials[idx].set_shader_parameter("moisture_frac", moisture_frac)


func _update_crop_visuals(idx: int) -> void:
	# LOD: adjust leaf segments based on camera distance to tile
	var cam: Camera3D = get_viewport().get_camera_3d()
	if cam:
		var tile_pos: Vector3 = _crop_sprites[idx][0].global_position
		var cam_dist: float = cam.global_position.distance_to(tile_pos)
		CropRenderer3D.leaf_segments = CropRenderer3D.leaf_segments_for_distance(cam_dist)
	CropVisuals.update_crop(
		_tile_data[idx], _crop_sprites[idx], CROP_GRID, TILE_SIZE, METERS_PER_TILE
	)
	# Apply current wind to crop plants
	var container: Node3D = _crop_sprites[idx][0]
	CropRenderer3D.set_wind(container, _wind_strength, _wind_dir)


func _on_debug_wind(strength: float, direction: Vector2) -> void:
	_wind_strength = strength
	_wind_ms = strength * WIND_SCALE_MAX_MS
	_wind_dir = direction
	FarmViewDebug.apply_wind_to_all_crops(_crop_sprites, _wind_strength, _wind_dir)
	rain.set_wind(_wind_ms, _wind_dir)


func _on_debug_rain(raining: bool, intensity: float) -> void:
	rain.set_raining(raining, intensity)


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
			print("[GAME] created new game: %s" % _game_id)
			callback.call()
	)


func _set_buttons_disabled(disabled: bool) -> void:
	_bar_held = disabled
	next_day_btn.disabled = disabled
	ff7_btn.disabled = disabled
	ff_all_btn.disabled = disabled
	irrigate_btn.disabled = disabled
	fertilize_btn.disabled = disabled
	tillage_btn.disabled = disabled
	lime_btn.disabled = disabled
	plant_btn.disabled = disabled
	# Harvest stays gated on crop presence even when re-enabling the bar.
	if disabled:
		harvest_btn.disabled = true
	else:
		_releases += 1
		_update_harvest_button()


func _selected_has_standing_crop() -> bool:
	## True when the selected tile carries a crop that has not been harvested.
	if _selected_tile.x < 0:
		return false
	var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
	if idx < 0 or idx >= _tile_data.size():
		return false
	var data: Dictionary = _tile_data[idx]
	var crop_key: String = data.get("crop_key", "")
	var crop_stage: int = data.get("crop_stage", 0)
	return not crop_key.is_empty() and crop_stage > 0


func _update_harvest_button() -> void:
	## Enable Harvest only for a selected patch with a standing crop; otherwise
	## disable with an explanatory tooltip.
	if _selected_has_standing_crop():
		harvest_btn.disabled = _bar_held
		harvest_btn.tooltip_text = "Harvest the standing crop on this patch"
	else:
		harvest_btn.disabled = true
		if _selected_tile.x < 0:
			harvest_btn.tooltip_text = "Select a patch with a standing crop to harvest"
		else:
			harvest_btn.tooltip_text = "No standing crop to harvest on this patch"


func _on_next_day() -> void:
	_ensure_game(func() -> void: _step_days(1))


func _on_ff7() -> void:
	_ensure_game(func() -> void: _step_days(7))


func _on_ff_all() -> void:
	_ensure_game(
		func() -> void:
			_set_buttons_disabled(true)
			_api_client.run_season(_game_id, _on_season_complete)
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
	_api_client.get_forecast(_game_id, FarmLayout.FIELD_ID, _on_forecast_received)
	_refresh_action_costs()
	if _cutaway.is_active() and _selected_tile.x >= 0:
		_show_soil_cutaway()


func _refresh_action_costs() -> void:
	## Preview each fixed-cost action so buttons show cost + block if unaffordable.
	if _game_id.is_empty():
		return
	_previews.refresh(_game_id, FarmLayout.FIELD_ID)


func _on_weather_clicked(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		forecast_panel.visible = not forecast_panel.visible
		if forecast_panel.visible:
			var bottom_bar: PanelContainer = $UILayer/BottomBar
			var vp_h: float = get_viewport().get_visible_rect().size.y
			var bar_h: float = bottom_bar.size.y
			forecast_panel.offset_left = 16.0
			forecast_panel.offset_bottom = vp_h - bar_h - 8.0
			forecast_panel.offset_top = forecast_panel.offset_bottom - 180.0
			forecast_panel.offset_right = 256.0


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
	_balance_credits = balance
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
	# Wind from weather data — drive crop sway + rain angle
	_wind_ms = w.get("wind_m_s", 2.0)
	_wind_strength = clampf(_wind_ms / WIND_SCALE_MAX_MS, WIND_MIN_STRENGTH, 1.0)
	# Random wind direction per day (seeded by day number for consistency)
	var day_seed: float = fmod(float(day_num) * 2.399, TAU)
	_wind_dir = Vector2(cos(day_seed), sin(day_seed))
	rain.set_raining(rain_mm > 1.0, rain_mm)
	rain.set_wind(_wind_ms, _wind_dir)
	FarmViewDebug.update_weather_lighting(w, sun, env, fog_clouds)
	# Update all crop plants with current wind
	FarmViewDebug.apply_wind_to_all_crops(_crop_sprites, _wind_strength, _wind_dir)

	var snapshots: Array = data.get("daily_snapshots", [])
	FarmViewHistory.append_snapshots(snapshots, _daily_history, _layout)

	var patches: Dictionary = data.get("patches", {})
	if ProjectSettings.get_setting("agrogame/debug/stress_events", false):
		FarmViewDebug.inject_debug_stress_events(patches)
	_apply_patch_data(patches, not snapshots.is_empty())


func _apply_patch_data(patches: Dictionary, skip_history: bool = false) -> void:
	for field_id: String in patches:
		var patch_list: Array = patches[field_id]
		for patch_idx in range(patch_list.size()):
			var patch: Dictionary = patch_list[patch_idx]
			# Tile writes live in FarmTiles (#546); refreshes stay here, tile order.
			var written := FarmTiles.write_patch(patch, field_id, patch_idx, _tile_data)
			# History for a laid-out patch (skip when daily_snapshots covered it)
			if not skip_history and not written.is_empty():
				FarmViewHistory.append_patch(patch, field_id, patch_idx, _daily_history)
			for i: int in written:
				_update_tile_shader(i)
				_update_crop_visuals(i)
	# Update stress icons from patch events
	if _stress_icons:
		_stress_icons.update_from_patches(patches, _tile_data, _tile_meshes)
	if _selected_tile.x >= 0:
		var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
		_cutaway.update_tile_info(_daily_history.get(FarmLayout.tile_key(_tile_data[idx]), []))
	# Crop stage may have changed (e.g. reached maturity or was cleared).
	_update_harvest_button()
	_refresh_quick_status()


## Every /action goes out here, holding the bar until its reply, and for all
## but Harvest the step that reply triggers, has been applied (#534).
func _send_action(field_id: String, action: String, params: Dictionary, on_reply: Callable) -> void:
	_set_buttons_disabled(true)
	_api_client.execute_action(_game_id, field_id, action, params, on_reply)


## Irrigate, Fertilize, Tillage and Lime act on a whole field: FIELD_ID until
## the active field (#601). Plant and Harvest name the selected tile's.
func _send_field_action(action: String, params: Dictionary) -> void:
	_send_action(FarmLayout.FIELD_ID, action, params, _on_action_complete)


func _on_irrigate() -> void:
	_ensure_game(func() -> void: _send_field_action("irrigate", {"amount_mm": 20}))


func _setup_fertilizer_popup() -> void:
	_fertilizer_popup = PopupMenu.new()
	for i in range(FertilizerPicker.option_count()):
		# Separate the picker into per-type groups for readability.
		if FertilizerPicker.starts_new_group(i):
			_fertilizer_popup.add_separator()
		_fertilizer_popup.add_item(FertilizerPicker.label_for(i), i)
	_fertilizer_popup.id_pressed.connect(_on_fertilizer_selected)
	UiTheme.style_popup_menu(_fertilizer_popup)
	$UILayer.add_child(_fertilizer_popup)


func _on_fertilize() -> void:
	_apply_item_affordability()
	var btn_rect := fertilize_btn.get_global_rect()
	_fertilizer_popup.position = Vector2i(int(btn_rect.position.x), int(btn_rect.end.y))
	_fertilizer_popup.popup()


func _apply_item_affordability() -> void:
	## Grey out picker tiers the player cannot afford, so a selection never
	## previews one price then hits a backend 400 for another (#349 review).
	## Balance unknown (< 0, before any preview) leaves every tier selectable.
	for idx in range(_fertilizer_popup.item_count):
		if _fertilizer_popup.is_item_separator(idx):
			continue
		var option_id: int = _fertilizer_popup.get_item_id(idx)
		var affordable: bool = (
			_balance_credits < 0 or FertilizerPicker.is_affordable(option_id, _balance_credits)
		)
		_fertilizer_popup.set_item_disabled(idx, not affordable)


func _on_fertilizer_selected(option_id: int) -> void:
	var params: Dictionary = FertilizerPicker.params_for(option_id)
	if params.is_empty():
		return
	var fert_type: String = params["type"]
	var amount: float = params["amount_kg_ha"]
	var cost: int = FertilizerPicker.cost_for(fert_type, amount)
	var display_name: String = FertilizerPicker.LABELS.get(fert_type, fert_type)
	# Rate is kg of nutrient element, not kg of product (#508).
	var unit: String = FertilizerPicker.unit_for(fert_type)
	_ensure_game(
		func() -> void:
			status_label.text = (
				"Applying %s %d %s — est. %d credits" % [display_name, int(amount), unit, cost]
			)
			_send_field_action("fertilize", params)
	)


func _setup_lime_popup() -> void:
	## Lime gets its own picker: t/ha tiers, not the fertiliser kg/ha tiers (#465).
	_lime_popup = LimePopup.new()
	_lime_popup.rate_selected.connect(_on_lime_selected)
	UiTheme.style_popup_menu(_lime_popup)
	$UILayer.add_child(_lime_popup)


func _on_lime() -> void:
	_lime_popup.apply_affordability(_balance_credits)
	_lime_popup.popup_under(lime_btn)


func _on_lime_selected(amount_kg_ha: float, cost: int) -> void:
	var params := {"amount_kg_ha": amount_kg_ha, "layer": LimePicker.TARGET_LAYER}
	_ensure_game(
		func() -> void:
			status_label.text = (
				"Applying lime %.1f t/ha — est. %d credits" % [amount_kg_ha / 1000.0, cost]
			)
			_send_field_action("lime", params)
	)


func _on_tillage() -> void:
	_ensure_game(func() -> void: _send_field_action("tillage", {"intensity": 0.8}))


func _on_harvest_pressed() -> void:
	if not _selected_has_standing_crop():
		status_label.text = "Select a patch with a standing crop to harvest"
		return
	var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
	var crop_key: String = _tile_data[idx].get("crop_key", "")
	var field_id := _selected_field()
	var patch_idx: int = _tile_data[idx]["patch_idx"]
	var on_reply := _on_harvest_complete.bind(crop_key, field_id, patch_idx)
	var params := {"patch_idx": patch_idx}
	_ensure_game(func() -> void: _send_action(field_id, "harvest", params, on_reply))


func _on_harvest_complete(
	success: bool, data: Dictionary, crop_key: String, field_id: String, patch_idx: int
) -> void:
	_set_buttons_disabled(false)
	if not success:
		_reconcile("Harvest failed")
		return
	var cost: int = data.get("cost_credits", 0)
	credits_label.text = "%d" % data.get("balance_credits", 0)
	# Backend really settled + cleared the crop, so this clear survives /step.
	for i: int in FarmLayout.tiles_of(field_id, patch_idx, _tile_data):
		_tile_data[i]["crop_key"] = ""
		_tile_data[i]["crop_stage"] = 0
		_tile_data[i]["lai"] = 0.0
		_tile_data[i]["grain_g_m2"] = 0.0
		_update_crop_visuals(i)
	_refresh_quick_status()
	# Yield + P&L come straight from the harvest action's settlement response.
	var grain_g_m2: float = data.get("grain_g_m2", 0.0)
	status_label.text = (
		"Harvested %s: %.0f g/m² grain (cost %d credits) — revenue %d | profit %d credits"
		% [
			crop_key,
			grain_g_m2,
			cost,
			int(data.get("revenue_credits", 0)),
			int(data.get("profit_credits", 0)),
		]
	)
	_update_harvest_button()
	# The action response is authoritative for P&L; fetch the season report only
	# to confirm the fuller breakdown is available and note the gap if it is not.
	_api_client.get_report(_game_id, _on_harvest_report_received)


func _on_harvest_report_received(success: bool, _data: Dictionary) -> void:
	# Report failure (e.g. mid-season 400) just notes the gap; P&L already shown.
	if not success:
		status_label.text += " (detailed report unavailable)"


func _setup_crop_popup() -> void:
	_crop_popup = CropPopup.new(AVAILABLE_CROPS)
	_crop_popup.id_pressed.connect(_on_crop_selected)
	UiTheme.style_popup_menu(_crop_popup)
	$UILayer.add_child(_crop_popup)


func _on_plant_pressed() -> void:
	if _selected_tile.x < 0:
		status_label.text = "Select a tile first to plant"
		return
	_crop_popup.refresh_costs(_api_client, _game_id, _selected_field(), _plant_params)
	var btn_rect := plant_btn.get_global_rect()
	_crop_popup.position = Vector2i(int(btn_rect.position.x), int(btn_rect.end.y))
	_crop_popup.popup()


func _plant_params(crop_key: String) -> Dictionary:
	## What planting `crop_key` on the selected tile sends; the crop popup
	## previews the same params, so each item's cost is the charge (#525).
	var idx := _selected_tile.y * GRID_COLS + _selected_tile.x
	return {"crop_key": crop_key, "patch_idx": _tile_data[idx]["patch_idx"]}


func _selected_field() -> String:
	## The field of the selected tile, which Plant and Harvest act on (#600).
	return _tile_data[_selected_tile.y * GRID_COLS + _selected_tile.x]["field_id"]


func _on_crop_selected(id: int) -> void:
	if id < 0 or id >= AVAILABLE_CROPS.size():
		return
	var crop_key: String = AVAILABLE_CROPS[id]
	var params := _plant_params(crop_key)
	var field_id := _selected_field()
	var on_reply := _on_plant_complete.bind(crop_key, field_id, params["patch_idx"])
	_ensure_game(func() -> void: _send_action(field_id, "plant", params, on_reply))


func _on_plant_complete(
	success: bool, data: Dictionary, crop_key: String, field_id: String, patch_idx: int
) -> void:
	if not success:
		_set_buttons_disabled(false)
		_reconcile("Plant failed")
		return
	var cost: int = data.get("cost_credits", 0)
	credits_label.text = "%d" % data.get("balance_credits", 0)
	for i: int in FarmLayout.tiles_of(field_id, patch_idx, _tile_data):
		_tile_data[i]["crop_key"] = crop_key
		_tile_data[i]["crop_stage"] = 1
		_tile_data[i]["lai"] = 0.0
		_update_crop_visuals(i)
	_refresh_quick_status()
	status_label.text = "Planted %s — %d credits" % [crop_key, cost]
	_step_days(1)


func _on_action_complete(success: bool, data: Dictionary) -> void:
	if not success:
		_set_buttons_disabled(false)
		_reconcile("Action failed")
		return
	var action: String = data.get("action", "")
	var cost: int = data.get("cost_credits", 0)
	credits_label.text = "Credits: %d" % data.get("balance_credits", 0)
	status_label.text = "%s — %d credits" % [action, cost]
	_step_days(1)


## Show `failure` and re-read the game, which the server may have changed anyway (#564).
func _reconcile(failure: String) -> void:
	status_label.text = failure
	_api_client.get_game(_game_id, _on_reconciled.bind(failure, _releases))


## Take the server's balance and crops as the truth, unless a newer reply has released the bar.
func _on_reconciled(ok: bool, data: Dictionary, failure: String, releases: int) -> void:
	if not ok or releases != _releases or not data.has("balance_credits"):
		return
	status_label.text = "%s; credits and crops re-read from the server" % failure
	_balance_credits = data["balance_credits"]
	credits_label.text = "%d" % _balance_credits
	for i: int in FarmTiles.reconcile_crops(data.get("fields", {}), _tile_data):
		_update_crop_visuals(i)
	_update_harvest_button()
	_refresh_quick_status()
	_refresh_action_costs()


func _on_season_complete(success: bool, data: Dictionary) -> void:
	_on_step_complete(success, data)  # final /step result: show end-of-season state
	status_label.text = "Season complete" if success else "Season failed — backend error"


func _on_soil_view() -> void:
	if _selected_tile.x < 0:
		status_label.text = "Select a tile first to view soil"
		return
	if _last_step_data.is_empty():
		status_label.text = "Step at least 1 day to see soil data"
		return
	_show_soil_cutaway()


func _show_soil_cutaway() -> void:
	var ctx := {
		"selected": _selected_tile,
		"tile_data": _tile_data,
		"tile_meshes": _tile_meshes,
		"crop_sprites": _crop_sprites,
		"patches": _last_step_data.get("patches", {}),
		"grid_cols": GRID_COLS,
		"grid_rows": GRID_ROWS,
		"update_crop_fn": _update_crop_visuals,
	}
	if not _cutaway.show_cutaway(ctx, self, $UILayer):
		status_label.text = "No soil data available"


func _start_debug_driver() -> void:
	## Hand the debug demo driver the callables it needs to drive this view.
	_debug.start(
		{
			"api": _api_client,
			"game_id_fn": func() -> String: return _game_id,
			"ensure_game_fn": _ensure_game,
			"apply_step_fn": _apply_debug_step,
			"select_tile_fn": _select_tile,
			"show_cutaway_fn": _show_soil_cutaway,
		}
	)


func _apply_debug_step(data: Dictionary) -> void:
	## Cache the demo step result and refresh the view from it.
	_last_step_data = data
	_apply_day_result(data)
