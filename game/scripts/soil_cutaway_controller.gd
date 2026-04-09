class_name SoilCutawayController
extends RefCounted
## Manages soil cutaway display: pillar selection, front-tile hiding,
## nutrient panel, and tile info panel lifecycle.

const SoilView = preload("res://scripts/soil_view.gd")

var _soil_view: Node3D = null
var _nutrient_panel: PanelContainer = null
var _tile_info_panel: PanelContainer = null
var _cycle_panel: PanelContainer = null
var _cycle_label: Label = null
var _hidden_tiles: Array[int] = []


func show_cutaway(ctx: Dictionary, parent_3d: Node3D, ui_layer: CanvasLayer) -> bool:
	"""Build and display the soil cutaway. Returns false if no data.

	ctx keys: selected, tile_data, tile_meshes, crop_sprites, patches,
	grid_cols, grid_rows, soil_types, update_crop_fn.
	"""
	var selected: Vector2i = ctx["selected"]
	var tile_data: Array = ctx["tile_data"]
	var tile_meshes: Array = ctx["tile_meshes"]
	var crop_sprites: Array = ctx["crop_sprites"]
	var patches: Dictionary = ctx["patches"]
	var grid_cols: int = ctx["grid_cols"]
	var grid_rows: int = ctx["grid_rows"]
	var soil_types: Array = ctx["soil_types"]
	var update_crop_fn: Callable = ctx["update_crop_fn"]
	restore_hidden_tiles(tile_meshes, crop_sprites, update_crop_fn)
	var col := selected.x
	var row := selected.y
	var front_tiles: Array[Vector2i] = [
		Vector2i(col + 1, row),
		Vector2i(col, row + 1),
		Vector2i(col + 1, row + 1),
	]
	var pillar_tiles: Array[Vector2i] = [
		Vector2i(col, row),
		Vector2i(col - 1, row + 1),
		Vector2i(col + 1, row - 1),
	]
	_hidden_tiles.clear()
	for pos in front_tiles:
		if _is_valid(pos, grid_cols, grid_rows):
			var idx: int = pos.y * grid_cols + pos.x
			_hidden_tiles.append(idx)
			tile_meshes[idx].visible = false
			for spr in crop_sprites[idx]:
				spr.visible = false
	var columns: Array[Dictionary] = []
	for i in range(pillar_tiles.size()):
		var tp := pillar_tiles[i]
		if not _is_valid(tp, grid_cols, grid_rows):
			continue
		var col_data := _get_soil_column(
			tp, patches, i == 0, tile_data, tile_meshes, grid_cols, soil_types
		)
		if not col_data.is_empty():
			columns.append(col_data)
	if columns.is_empty():
		restore_hidden_tiles(tile_meshes, crop_sprites, update_crop_fn)
		return false
	if not _soil_view:
		_soil_view = Node3D.new()
		_soil_view.set_script(SoilView)
		parent_3d.add_child(_soil_view)
	_soil_view.show_cutaway(columns)
	_show_nutrient_panel(columns, ui_layer)
	_show_cycle_panel(ui_layer)
	return true


func hide_cutaway(
	tile_meshes: Array[MeshInstance3D],
	crop_sprites: Array[Array],
	update_crop_fn: Callable,
) -> void:
	if _soil_view and _soil_view.is_active():
		_soil_view.hide_view()
	hide_nutrient_panel()
	_hide_cycle_panel()
	restore_hidden_tiles(tile_meshes, crop_sprites, update_crop_fn)


func is_active() -> bool:
	return _soil_view != null and _soil_view.is_active()


func restore_hidden_tiles(
	tile_meshes: Array[MeshInstance3D],
	crop_sprites: Array[Array],
	update_crop_fn: Callable,
) -> void:
	for idx in _hidden_tiles:
		tile_meshes[idx].visible = true
		var container: Node3D = crop_sprites[idx][0]
		container.visible = true
		update_crop_fn.call(idx)
	_hidden_tiles.clear()


func show_tile_info(
	soil_type: String, crop_key: String, history: Array, ui_layer: CanvasLayer
) -> void:
	hide_tile_info()
	var TileInfoPanel := preload("res://scripts/tile_info_panel.gd")
	_tile_info_panel = PanelContainer.new()
	_tile_info_panel.set_script(TileInfoPanel)
	_tile_info_panel.position = Vector2(16, 40)
	_tile_info_panel.size = Vector2(240, 0)
	_tile_info_panel.show_history(history, soil_type, crop_key)
	ui_layer.add_child(_tile_info_panel)


func update_tile_info(history: Array) -> void:
	if _tile_info_panel and _tile_info_panel.visible:
		_tile_info_panel.update_history(history)


func hide_tile_info() -> void:
	if _tile_info_panel:
		_tile_info_panel.queue_free()
		_tile_info_panel = null


func hide_nutrient_panel() -> void:
	if _nutrient_panel:
		_nutrient_panel.queue_free()
		_nutrient_panel = null


static func _is_valid(pos: Vector2i, cols: int, rows: int) -> bool:
	return pos.x >= 0 and pos.x < cols and pos.y >= 0 and pos.y < rows


func _get_soil_column(
	tp: Vector2i,
	patches: Dictionary,
	is_center: bool,
	tile_data: Array[Dictionary],
	tile_meshes: Array[MeshInstance3D],
	grid_cols: int,
	soil_types: Array[String],
) -> Dictionary:
	var idx: int = tp.y * grid_cols + tp.x
	var soil_type: String = tile_data[idx]["soil_type"]
	var patch_idx := soil_types.find(soil_type)
	if patch_idx < 0:
		patch_idx = 0
	var soil_state := {}
	var root_depth_cm := 0.0
	var events: Array = []
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		var pi: int = patch_idx if patch_idx < patch_list.size() else 0
		if pi < patch_list.size():
			var patch: Dictionary = patch_list[pi]
			soil_state = patch.get("soil_state", {})
			root_depth_cm = patch.get("root_depth_cm", 0.0)
			events = patch.get("events", [])
			print("[COL] field=%s pi=%d events=%d" % [field_key, pi, events.size()])
	if soil_state.is_empty():
		return {}
	var crop_key: String = tile_data[idx].get("crop_key", "")
	return {
		"pos": tile_meshes[idx].position,
		"soil_state": soil_state,
		"profile": SoilView.get_profile_layers(soil_type),
		"root_depth_cm": root_depth_cm if is_center else 0.0,
		"crop_key": crop_key,
		"show_info": is_center,
		"events": events if is_center else [],
	}


func _show_nutrient_panel(columns: Array[Dictionary], ui_layer: CanvasLayer) -> void:
	hide_nutrient_panel()
	var NutrientPanel := preload("res://scripts/nutrient_panel.gd")
	_nutrient_panel = PanelContainer.new()
	_nutrient_panel.set_script(NutrientPanel)
	var vp: Viewport = ui_layer.get_viewport()
	_nutrient_panel.position = Vector2(vp.get_visible_rect().size.x - 280, 70)
	_nutrient_panel.size = Vector2(260, 0)
	var layers_data: Array[Dictionary] = []
	for col_data: Dictionary in columns:
		if not col_data.get("show_info", false):
			continue
		var soil_state: Dictionary = col_data.get("soil_state", {})
		var profile: Array = col_data.get("profile", [])
		var no3: Array = soil_state.get("n_no3", [])
		var nh4: Array = soil_state.get("n_nh4", [])
		var p: Array = soil_state.get("p_available", [])
		var som: Array = soil_state.get("som_labile_c", [])
		var theta: Array = soil_state.get("water_theta", [])
		var ph: Array = soil_state.get("ph", [])
		var mic: Array = soil_state.get("microbe_c", [])
		for i in range(profile.size()):
			var depth: int = profile[i].get("depth_cm", 30)
			var vals := {
				"NO₃": no3[i] if i < no3.size() else 0.0,
				"NH₄": nh4[i] if i < nh4.size() else 0.0,
				"P": p[i] if i < p.size() else 0.0,
				"SOM": som[i] if i < som.size() else 0.0,
				"Water": theta[i] if i < theta.size() else 0.0,
				"pH": ph[i] if i < ph.size() else 6.5,
				"Microbe": mic[i] if i < mic.size() else 0.0,
			}
			var lbl := "%d–%dcm" % [0 if i == 0 else depth, depth]
			layers_data.append({"depth_label": lbl, "values": vals})
	_nutrient_panel.show_layers(layers_data)
	_nutrient_panel.visible = true
	ui_layer.add_child(_nutrient_panel)


func _show_cycle_panel(ui_layer: CanvasLayer) -> void:
	_hide_cycle_panel()
	_cycle_panel = PanelContainer.new()
	_cycle_panel.add_theme_stylebox_override("panel", UiTheme.create_panel_style(true))
	UiTheme.add_blur_bg(_cycle_panel)
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	_cycle_panel.add_child(vbox)
	# Cycle view title label
	_cycle_label = Label.new()
	_cycle_label.text = "ALL FLOWS"
	_cycle_label.uppercase = true
	_cycle_label.add_theme_font_size_override("font_size", 10)
	_cycle_label.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	_cycle_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(_cycle_label)
	# Filter buttons row
	var btn_row := HBoxContainer.new()
	btn_row.add_theme_constant_override("separation", 2)
	btn_row.alignment = BoxContainer.ALIGNMENT_CENTER
	vbox.add_child(btn_row)
	var colors := {
		"all": UiTheme.TEXT_PRIMARY,
		"water": UiTheme.SUBSTANCE_WATER,
		"nitrogen": UiTheme.SUBSTANCE_NO3,
		"carbon": UiTheme.SUBSTANCE_CARBON,
		"phosphorus": UiTheme.SUBSTANCE_PHOSPHORUS,
	}
	var labels := {"all": "All", "water": "H₂O", "nitrogen": "N", "carbon": "C", "phosphorus": "P"}
	for fkey: String in FlowOverlay.CYCLE_FILTERS:
		var btn := Button.new()
		btn.text = labels.get(fkey, fkey)
		btn.custom_minimum_size = Vector2(36, 24)
		UiTheme.style_button(btn)
		btn.add_theme_font_size_override("font_size", 10)
		var col: Color = colors.get(fkey, UiTheme.TEXT_PRIMARY)
		btn.add_theme_color_override("font_color", col)
		btn.add_theme_color_override("font_hover_color", col.lightened(0.3))
		btn.pressed.connect(_on_cycle_filter.bind(fkey))
		btn_row.add_child(btn)
	# Toggle button
	var toggle := Button.new()
	toggle.text = "👁"
	toggle.custom_minimum_size = Vector2(28, 24)
	UiTheme.style_button(toggle)
	toggle.add_theme_font_size_override("font_size", 10)
	toggle.pressed.connect(_on_toggle_overlay)
	btn_row.add_child(toggle)
	_cycle_panel.position = Vector2(16, 16)
	_cycle_panel.size = Vector2(0, 0)
	ui_layer.add_child(_cycle_panel)


func _hide_cycle_panel() -> void:
	if _cycle_panel:
		_cycle_panel.queue_free()
		_cycle_panel = null
		_cycle_label = null


func _on_cycle_filter(filter_name: String) -> void:
	if _soil_view and _soil_view.has_method("get_flow_overlay"):
		var overlay: FlowOverlay = _soil_view.get_flow_overlay()
		if overlay:
			overlay.set_filter(filter_name)
	if _cycle_label:
		_cycle_label.text = FlowOverlay.CYCLE_LABELS.get(filter_name, "ALL FLOWS")


func _on_toggle_overlay() -> void:
	if _soil_view and _soil_view.has_method("get_flow_overlay"):
		var overlay: FlowOverlay = _soil_view.get_flow_overlay()
		if overlay:
			overlay.set_overlay_visible(not overlay.is_overlay_visible())
