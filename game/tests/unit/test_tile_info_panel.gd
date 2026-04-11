extends GutTest

const TileInfoPanel = preload("res://scripts/tile_info_panel.gd")


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
	assert_eq(TileInfoPanel.GRAPHS.size(), 10, "10 graph keys")
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
