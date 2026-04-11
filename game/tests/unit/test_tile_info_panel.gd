extends GutTest

const TileInfoPanel = preload("res://scripts/tile_info_panel.gd")


func test_graphs_defined() -> void:
	assert_eq(TileInfoPanel.GRAPHS.size(), 10, "10 graph configs")
	for key: String in [
		"lai",
		"grain_g_m2",
		"water_stress",
		"theta_surface",
		"n_available",
		"redox_eh_surface",
		"fe_available_surface",
		"zn_available_surface",
		"mn_available_surface",
		"agg_mwd_surface",
	]:
		assert_true(TileInfoPanel.GRAPHS.has(key), "Graph for %s" % key)


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
	assert_eq(transitions.size(), 2, "Two transitions: planted→veg, veg→flower")
	assert_eq(transitions[0], 2)
	assert_eq(transitions[1], 4)


func test_extract_series_missing_key() -> void:
	var history := [{"lai": 1.0}, {"lai": 2.0}]
	var data := TileInfoPanel._extract_series(history, "nonexistent")
	assert_eq(data.size(), 2)
	assert_eq(data[0], 0.0, "Missing key defaults to 0")
