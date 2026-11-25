class_name SoilPanelController
extends RefCounted
## The Soil Analysis panel that View Soil opens, and the tile-info (history)
## panel behind the Quick Status card's history button (#647, ADR-022). The
## panel shows the selected tile's own (field, patch) and refreshes in place.

const NutrientPanel = preload("res://scripts/nutrient_panel.gd")
const OrganicCarbonSummary = preload("res://scripts/organic_carbon_summary.gd")
const TileInfoPanel = preload("res://scripts/tile_info_panel.gd")
const PANEL_NAME := "SoilAnalysisPanel"
const WIDTH := 260.0
const MARGIN := 16.0  # from the screen's top and right edges and the bottom bar
## Row label -> the soil_state array it reads, and the value shown where a
## layer lacks one (as the cutaway's column builder showed them).
const ROW_KEYS := {
	"NO₃": ["n_no3", 0.0],
	"NH₄": ["n_nh4", 0.0],
	"P": ["p_available", 0.0],
	"Water": ["water_theta", 0.0],
	"pH": ["ph", 6.5],
	"Microbe": ["microbe_c", 0.0],
	"MicrobeN": ["microbe_n", 0.0],
	"Fungal": ["fungal_fraction", 0.0],
	"Fe": ["fe_available", 10.0],
	"Zn": ["zn_available", 1.2],
	"Mn": ["mn_available", 18.0],
	"Eh": ["redox_eh", 400.0],
	"MWD": ["agg_mwd", 1.0],
}

var _nutrient_panel: PanelContainer = null
var _tile_info_panel: PanelContainer = null


func is_open() -> bool:
	return _nutrient_panel != null


## Open the panel for `tile`'s own (field_id, patch_idx) in a /step payload's
## `patches`, or refresh it in place, keeping which layers are open. Its bottom
## stays MARGIN above `bottom_bar`. Closes it and returns false when the payload
## lacks that patch or its soil: never another field's or index's (#516, #600).
func show_panel(
	patches: Dictionary, tile: Dictionary, ui_layer: CanvasLayer, bottom_bar: Control
) -> bool:
	var field_id: String = tile.get("field_id", "")
	var patch_idx: int = tile.get("patch_idx", -1)
	var patch_list: Array = patches.get(field_id, [])
	var soil_state: Dictionary = {}
	if patch_idx >= 0 and patch_idx < patch_list.size():
		soil_state = (patch_list[patch_idx] as Dictionary).get("soil_state", {})
	if soil_state.is_empty():
		hide_nutrient_panel()
		return false
	if _nutrient_panel == null:
		_nutrient_panel = PanelContainer.new()
		_nutrient_panel.name = PANEL_NAME
		_nutrient_panel.set_script(NutrientPanel)
		_nutrient_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
		ui_layer.add_child(_nutrient_panel)
		_nutrient_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
		_nutrient_panel.offset_left = -WIDTH - MARGIN
		_nutrient_panel.offset_right = -MARGIN
		_nutrient_panel.offset_top = MARGIN
		_nutrient_panel.offset_bottom = MARGIN  # hug the rows: grow down to the minimum
	_nutrient_panel.max_height = top_of(bottom_bar) - 2.0 * MARGIN
	var layers := layers_data(soil_state)
	var biomass := {
		"root_g_m2": soil_state.get("root_biomass_g_m2", 0.0),
		"stem_g_m2": soil_state.get("stem_biomass_g_m2", 0.0),
	}
	_nutrient_panel.show_layers(layers, biomass)
	print("[SOIL] panel field=%s patch=%d layers=%d" % [field_id, patch_idx, layers.size()])
	return true


## The top of a bar anchored to the bottom, which grows up to its minimum size
## only on the frame after it changes: so the minimum, not the stale rect.
static func top_of(bar: Control) -> float:
	var rect := bar.get_global_rect()
	return minf(rect.position.y, rect.end.y - bar.get_combined_minimum_size().y)


func hide_nutrient_panel() -> void:
	if _nutrient_panel:
		_nutrient_panel.queue_free()
		_nutrient_panel = null


## The panel's rows for each layer of `soil_state`, top down. Depth labels come
## from `layer_thickness_cm` (#646), or read "Layer n" where it is missing.
static func layers_data(soil_state: Dictionary) -> Array[Dictionary]:
	var thickness: Array = soil_state.get("layer_thickness_cm", [])
	var count: int = thickness.size()
	for row: String in ROW_KEYS:
		count = maxi(count, (soil_state.get(ROW_KEYS[row][0], []) as Array).size())
	var acceptor: Array = soil_state.get("dominant_acceptor", [])
	var layers: Array[Dictionary] = []
	var top := 0.0
	for i in range(count):
		var vals := {}
		for row: String in ROW_KEYS:
			var values: Array = soil_state.get(ROW_KEYS[row][0], [])
			vals[row] = values[i] if i < values.size() else ROW_KEYS[row][1]
		var label := "Layer %d" % (i + 1)
		if i < thickness.size():
			label = "%d–%dcm" % [roundi(top), roundi(top + float(thickness[i]))]
			top += float(thickness[i])
		(
			layers
			. append(
				{
					"depth_label": label,
					"values": vals,
					"carbon_pools": OrganicCarbonSummary.pools_for_layer(soil_state, i),
					"dominant_acceptor": acceptor[i] if i < acceptor.size() else "O2",
				}
			)
		)
	return layers


func show_tile_info(
	soil_type: String, crop_key: String, history: Array, ui_layer: CanvasLayer, pos: Vector2
) -> void:
	hide_tile_info()
	_tile_info_panel = PanelContainer.new()
	_tile_info_panel.set_script(TileInfoPanel)
	_tile_info_panel.position = pos
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
