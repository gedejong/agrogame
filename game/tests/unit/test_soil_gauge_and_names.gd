extends GutTest
## #629: the soil gauge has no SOM term, and the soil is named by its preset.
## #660: it reads root-zone water, not surface theta.

const QSC = preload("res://scripts/quick_status_card.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")


func test_root_zone_gauge_ignores_som_and_surface_theta() -> void:
	# #629: SOM is not an input. #660: nor is the uncited surface-theta optimum;
	# the gauge reads available over total available water in the root zone.
	var base := {"theta_surface": 0.2, "crop_stage": 0, "root_zone_water_fraction": 0.5}
	var half: float = QSC.compute_scores(base)["root_zone"]
	for som: float in [0.0, 7345.0, 73450.0]:
		base["som_total_c_g_m2"] = som
		assert_eq(QSC.compute_scores(base)["root_zone"], half, "SOM %.0f is not an input" % som)
	for theta: float in [0.0, 0.16, 0.24, 0.5]:
		base["theta_surface"] = theta
		assert_eq(QSC.compute_scores(base)["root_zone"], half, "theta %.2f is not an input" % theta)
	assert_eq(half, 50.0)
	base["root_zone_water_fraction"] = 0.6
	assert_eq(QSC.compute_scores(base)["root_zone"], 60.0, "the fraction moves it")


func test_root_zone_gauge_is_labelled_for_what_it_measures() -> void:
	var labels: Array = QSC.GAUGE_DEFS.map(func(g: Dictionary) -> String: return g["label"])
	# "Root-zone water" widens the 200 px card to 208 px with four marks (#660 C4).
	assert_has(labels, "Root zone")
	assert_does_not_have(labels, "Soil moisture")
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
	var panel: PanelContainer = view._soil_panel._tile_info_panel
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
