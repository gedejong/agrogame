extends GutTest

const TileInfoPanel = preload("res://scripts/tile_info_panel.gd")
const QSC = preload("res://scripts/quick_status_card.gd")


func test_tabs_defined() -> void:
	assert_eq(TileInfoPanel.TABS.size(), 4, "4 tabs")
	for tab_name: String in ["Crop", "Water", "Nutrients", "Soil"]:
		assert_true(TileInfoPanel.TABS.has(tab_name), "Tab %s exists" % tab_name)


func test_max_sparklines_per_tab() -> void:
	for tab_name: String in TileInfoPanel.TABS:
		var count: int = TileInfoPanel.TABS[tab_name].size()
		assert_lte(count, 4, "Tab %s has ≤4 sparklines (has %d)" % [tab_name, count])
		assert_gt(count, 0, "Tab %s has ≥1 sparkline" % tab_name)


func test_graphs_backward_compat() -> void:
	assert_eq(TileInfoPanel.GRAPHS.size(), 12, "12 graph keys (#669: Water, Root zone)")
	assert_true(TileInfoPanel.GRAPHS.has("water"), "GRAPHS has the Water gauge")
	assert_true(TileInfoPanel.GRAPHS.has("root_zone"), "GRAPHS has the Root zone gauge")
	assert_false(TileInfoPanel.GRAPHS.has("water_stress"), "no Water stress series")
	assert_true(TileInfoPanel.GRAPHS.has("lai"), "GRAPHS has lai")
	assert_true(TileInfoPanel.GRAPHS.has("theta_surface"), "GRAPHS has theta")
	assert_true(TileInfoPanel.GRAPHS.has("mn_available_surface"), "GRAPHS has Mn")
	assert_true(TileInfoPanel.GRAPHS.has("agg_mwd_surface"), "GRAPHS has MWD")


func test_extract_series_empty() -> void:
	var data := TileInfoPanel._extract_series([], "lai")
	assert_eq(data.size(), 0, "Empty input = empty output")


func test_extract_series_values() -> void:
	var history := [{"lai": 1.0}, {"lai": 2.0}, {"lai": 3.0}]
	var data := TileInfoPanel._extract_series(history, "lai")
	assert_eq(data.size(), 3)
	assert_eq(data[2], 3.0)


func test_find_stage_transitions() -> void:
	var history := [
		{"crop_stage": "planted"},
		{"crop_stage": "planted"},
		{"crop_stage": "vegetative"},
		{"crop_stage": "vegetative"},
		{"crop_stage": "flowering"},
	]
	var transitions := TileInfoPanel._find_stage_transitions(history)
	assert_eq(transitions.size(), 2, "Two transitions")
	assert_eq(transitions[0], 2)
	assert_eq(transitions[1], 4)


func test_extract_series_missing_key() -> void:
	var history := [{"lai": 1.0}, {"lai": 2.0}]
	var data := TileInfoPanel._extract_series(history, "nonexistent")
	assert_eq(data.size(), 2)
	assert_eq(data[0], 0.0, "Missing key defaults to 0")


func test_total_sparkline_count() -> void:
	var total := 0
	for tab_name: String in TileInfoPanel.TABS:
		total += TileInfoPanel.TABS[tab_name].size()
	assert_gte(total, 9, "At least 9 sparklines across all tabs")
	assert_lte(total, 16, "At most 16 sparklines total")


func test_water_tab_is_the_two_gauges_and_the_topsoil() -> void:
	var tab: Array = TileInfoPanel.TABS["Water"]
	var shown: Array = tab.map(func(c: Dictionary) -> Array: return [c["key"], c["label"]])
	assert_eq(
		shown, [["water", "Water"], ["root_zone", "Root zone"], ["theta_surface", "Topsoil water"]]
	)
	assert_eq(tab[2]["unit"], "m³/m³")
	assert_true(tab[0]["gauge"] and tab[1]["gauge"], "both gauges print the card's integer")
	for key: String in TileInfoPanel.GRAPHS:
		assert_ne(TileInfoPanel.GRAPHS[key]["label"], "Water stress")


## The History panel's Water-tab texts after `patches`, one day each.
func _water_texts(patches: Array) -> Array:
	var history: Dictionary = {}
	for patch: Dictionary in patches:
		FarmViewHistory.append_patch(patch, "field_1", 0, history)
	var panel := PanelContainer.new()
	panel.set_script(TileInfoPanel)
	add_child_autofree(panel)
	panel.show_history(history["field_1/0"], "Sandy - Temperate", "maize")
	var out: Array = []
	for key: String in ["water", "root_zone", "theta_surface"]:
		out.append(panel._sparklines[key].label_text())
	return out


## A /step patch payload: today's Ks, root-zone fraction and topsoil θ.
func _patch(stage: String, ks: float, rzf: float, theta: float = 0.05) -> Dictionary:
	return {
		"crop_key": "maize",
		"crop_stage": stage,
		"soil_theta_surface": theta,
		"root_zone_water_fraction": rzf,
		"depletion_fraction_p": 0.55,
		"events": [{"event_type": "WaterStressComputed", "data": {"stress": ks}}],
	}


func test_water_tab_texts() -> void:
	assert_eq(
		_water_texts([_patch("vegetative", 0.46, 0.216)]),
		["Water: 46", "Root zone: 21", "Topsoil water: 0.05 m³/m³"]
	)
	assert_eq(_water_texts([_patch("vegetative", 0.9999999999999998, 1.3)])[0], "Water: 100")


func test_water_reads_dash_once_the_crop_does_not_stand() -> void:
	# The Sahel crop at maturity: the card shows "—" for Water, a number for
	# Root zone; so does the History, though its line plots every day.
	var texts := _water_texts([_patch("grain_fill", 0.2, 0.3), _patch("maturity", 1.0, 0.25)])
	assert_eq(texts.slice(0, 2), ["Water: —", "Root zone: 25"])


func test_update_history_keeps_the_dash_rule() -> void:
	var history: Dictionary = {}
	FarmViewHistory.append_patch(_patch("vegetative", 0.46, 0.5), "field_1", 0, history)
	var panel := PanelContainer.new()
	panel.set_script(TileInfoPanel)
	add_child_autofree(panel)
	panel.show_history(history["field_1/0"], "Sandy", "maize")
	FarmViewHistory.append_patch(_patch("maturity", 1.0, 0.5), "field_1", 0, history)
	panel.update_history(history["field_1/0"])
	assert_eq(panel._sparklines["water"].label_text(), "Water: —")
	FarmViewHistory.append_patch(_patch("vegetative", 0.35, 0.19), "field_1", 0, history)
	panel.update_history(history["field_1/0"])
	assert_eq(panel._sparklines["water"].label_text(), "Water: 35", "a new crop stands again")


func test_history_numbers_equal_the_cards() -> void:
	# C5: on any tile, the History Water and Root zone texts equal the card's
	# numbers whenever the card shows one. The tile is written as farm_view
	# writes it (FarmTiles.write_patch), the history as append_patch does.
	var days: Array = [
		_patch("vegetative", 0.46, 0.216),
		_patch("emerged", 0.9999999999999998, 1.3),
		_patch("flowering", 0.399, 0.449),
		_patch("grain_fill", 0.70, 0.0),
		_patch("vegetative", 0.0, 0.999),
		_patch("maturity", 0.1, 0.55),
		_patch("planted", 1.0, 0.8),
	]
	for day: Dictionary in days:
		var tiles: Array = [{"field_id": "field_1", "patch_idx": 0}]
		FarmTiles.write_patch(day, "field_1", 0, tiles)
		var card: QuickStatusCard = QSC.new()
		add_child_autofree(card)
		card.show_status(tiles[0], "Sandy - Temperate")
		var texts := _water_texts([day])
		var what: String = "%s Ks %s" % [day["crop_stage"], day["events"][0]["data"]["stress"]]
		assert_eq(texts[0], "Water: " + card._gauge_labels["water"].text, what)
		assert_eq(texts[1], "Root zone: " + card._gauge_labels["root_zone"].text, what)
