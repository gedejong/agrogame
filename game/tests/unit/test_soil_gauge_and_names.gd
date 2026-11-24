extends GutTest
## #629: the soil gauge has no SOM term, and the soil is named by its preset.

const QSC = preload("res://scripts/quick_status_card.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")


func test_soil_gauge_ignores_som_and_follows_theta() -> void:
	# #629: the SOM term is gone, so it neither saturates nor moves the gauge;
	# theta moves it by 20% around a typical value.
	var base := {"theta_surface": 0.2, "crop_stage": 0}
	var low: float = QSC.compute_scores(base)["soil"]
	for som: float in [0.0, 7345.0, 73450.0]:
		base["som_total_c_g_m2"] = som
		assert_eq(QSC.compute_scores(base)["soil"], low, "SOM %.0f is not an input" % som)
	var wetter: float = QSC.compute_scores({"theta_surface": 0.24, "crop_stage": 0})["soil"]
	var drier: float = QSC.compute_scores({"theta_surface": 0.16, "crop_stage": 0})["soil"]
	assert_gt(wetter, low, "+20% theta moves the gauge")
	assert_lt(drier, low, "-20% theta moves the gauge")
	assert_lt(low, 100.0, "no saturation at a typical theta")


func test_soil_gauge_is_labelled_for_what_it_measures() -> void:
	var labels: Array = QSC.GAUGE_DEFS.map(func(g: Dictionary) -> String: return g["label"])
	assert_has(labels, "Soil moisture")
	assert_does_not_have(labels, "Soil")


func test_card_title_uses_the_given_soil_name() -> void:
	var card := QSC.new()
	add_child_autofree(card)
	card.show_status({"crop_key": "maize", "crop_stage": 0}, "Loam - Temperate")
	assert_eq(card._tile_label.text, "Maize — Loam - Temperate")


func test_status_line_shows_soil_name_and_som_with_unit() -> void:
	# The loam tile reads "Loam - Temperate", not "organic"; SOM carries its
	# unit and is the API's g C/m2 (pools / 10), not kg C/ha.
	var loam := {
		"soil_profile_key": "loam_temperate",
		"soil_name": "Loam - Temperate",
		"crop_key": "maize",
		"climate_key": "c",
		"area_fraction": 1.0,
	}
	GameState.game_id = "g"
	var api := FarmViewTest.ApiStub.new()
	api.game_reply = [true, {"game_id": "g", "fields": {"field_1": [loam]}}]
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._apply_patch_data(
		{
			"field_1":
			[
				{
					"crop_key": "maize",
					"crop_stage": "vegetative",
					"soil_theta_surface": 0.11,
					"som_total_c_g_m2": 7345.4
				}
			]
		}
	)
	view._select_tile(0, 0)
	assert_eq(view.status_label.text, "[0,0] Loam - Temperate | maize | SOM 7,345 gC/m² | θ 0.11")
	assert_eq(view._quick_status._tile_label.text, "Maize — Loam - Temperate")
	view._on_quick_status_history()
	var panel: PanelContainer = view._cutaway._tile_info_panel
	var titles: Array = panel.find_children("*", "Label", true, false).filter(
		func(n: Label) -> bool: return n.text.contains("Loam - Temperate")
	)
	assert_eq(titles.size(), 1, "History panel title carries the soil name")
	assert_false(view.status_label.text.to_lower().contains("organic"))


func test_status_line_reads_the_selected_fields_soil_and_som() -> void:
	# Both fields have a patch 0; a tile in field_2 must show field_2's soil name
	# and SOM, not field_1 patch 0's (#600 addressing, #629 values).
	var fields := {
		"field_1":
		[
			{
				"soil_profile_key": "sandy_temperate",
				"soil_name": "Sandy - Temperate",
				"crop_key": "maize",
			}
		],
		"field_2":
		[
			{
				"soil_profile_key": "clay_temperate",
				"soil_name": "Clay - Temperate",
				"crop_key": "rice",
			}
		],
	}
	GameState.game_id = "g"
	var api := FarmViewTest.ApiStub.new()
	api.game_reply = [true, {"game_id": "g", "fields": fields}]
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	var day := {"crop_stage": "vegetative", "soil_theta_surface": 0.2}
	(
		view
		. _apply_patch_data(
			{
				"field_1": [day.merged({"crop_key": "maize", "som_total_c_g_m2": 7345.0})],
				"field_2": [day.merged({"crop_key": "rice", "som_total_c_g_m2": 12346.0})],
			}
		)
	)
	view._select_tile(0, 5)
	assert_eq(view.status_label.text, "[0,5] Clay - Temperate | rice | SOM 12,346 gC/m² | θ 0.20")
	view._select_tile(0, 0)
	assert_eq(view.status_label.text, "[0,0] Sandy - Temperate | maize | SOM 7,345 gC/m² | θ 0.20")
