extends GutTest
## Tests for SoilPanelController (#647): the Soil Analysis panel for a tile's
## own (field, patch), its depth labels, and the tile-info panel's lifecycle.

const ControllerRef = preload("res://scripts/soil_panel_controller.gd")


## A soil_state of `thickness` layers whose NO₃ is `no3` in every layer.
func _soil(thickness: Array, no3: float = 1.0) -> Dictionary:
	var values: Array = thickness.map(func(_t: float) -> float: return no3)
	return {"layer_thickness_cm": thickness, "n_no3": values}


## A bottom bar on `ui` whose top is at y = 654.
func _bar(ui: CanvasLayer) -> Control:
	var bar := Control.new()
	bar.position = Vector2(0, 654)
	bar.size = Vector2(1280, 66)
	ui.add_child(bar)
	return bar


func _labels(soil_state: Dictionary) -> Array:
	return ControllerRef.layers_data(soil_state).map(
		func(layer: Dictionary) -> String: return layer["depth_label"]
	)


func test_hide_tile_info_no_crash_when_empty() -> void:
	var ctrl := ControllerRef.new()
	ctrl.hide_tile_info()
	assert_false(ctrl.is_open())


func test_hide_nutrient_panel_no_crash_when_empty() -> void:
	var ctrl := ControllerRef.new()
	ctrl.hide_nutrient_panel()
	assert_false(ctrl.is_open())


func test_inspector_wires_each_layers_three_carbon_pools() -> void:
	var previous_unit: Variant = ProjectSettings.get_setting("agrogame/display/mass_unit")
	ProjectSettings.set_setting("agrogame/display/mass_unit", UiTheme.MASS_UNIT_GM2)
	var ctrl := ControllerRef.new()
	var ui := CanvasLayer.new()
	add_child_autofree(ui)
	# Patch 0 is another tile's: the panel must not read it.
	var patches := {
		"f":
		[
			{"soil_state": {"layer_thickness_cm": [30.0], "som_labile_c": [99999.0]}},
			{
				"soil_state":
				{
					"layer_thickness_cm": [30.0, 40.0],
					"som_labile_c": [100.0, 10.0],
					"som_intermediate_c": [200.0, 20.0],
					"som_stable_c": [700.0, 70.0],
				}
			},
		]
	}
	assert_true(ctrl.show_panel(patches, {"field_id": "f", "patch_idx": 1}, ui, _bar(ui)))
	await get_tree().process_frame
	var bodies: Array = ctrl._nutrient_panel._layer_bodies
	assert_eq(bodies.size(), 2)
	assert_eq(
		bodies[0].get_node("OrganicCarbonSummary/TotalRow/TotalCarbonValue").text, "100.0 gC/m²"
	)
	assert_eq(
		bodies[1].get_node("OrganicCarbonSummary/TotalRow/TotalCarbonValue").text, "10.0 gC/m²"
	)
	var panel: PanelContainer = ctrl._nutrient_panel
	assert_almost_eq(
		panel.get_global_rect().end.x, ui.get_viewport().get_visible_rect().end.x - 16.0, 1.0
	)
	ctrl.hide_nutrient_panel()
	ProjectSettings.set_setting("agrogame/display/mass_unit", previous_unit)


func test_tile_info_panel_opens_where_it_is_told() -> void:
	var ctrl := ControllerRef.new()
	var layer := CanvasLayer.new()
	add_child_autofree(layer)
	var pos := Vector2(224, 40)
	ctrl.show_tile_info("Loam", "maize", [], layer, pos)
	assert_eq(layer.get_child(0).position, pos)
	ctrl.hide_tile_info()


func test_depth_labels_come_from_layer_thickness() -> void:
	# sandy_subsaharan and clay_temperate, data/soils/presets.yaml (#646).
	assert_eq(_labels(_soil([20.0, 40.0, 50.0])), ["0–20cm", "20–60cm", "60–110cm"])
	assert_eq(_labels(_soil([30.0, 35.0, 40.0])), ["0–30cm", "30–65cm", "65–105cm"])
	var no_thickness := {"n_no3": [1.0, 2.0, 3.0]}
	assert_eq(_labels(no_thickness), ["Layer 1", "Layer 2", "Layer 3"])


func test_layer_values_read_each_layer_with_the_old_fallbacks() -> void:
	var soil := _soil([25.0, 35.0], 4.0)
	soil["ph"] = [5.2]
	soil["dominant_acceptor"] = ["NO3"]
	var layers := ControllerRef.layers_data(soil)
	assert_eq(layers[1]["values"]["NO₃"], 4.0)
	assert_eq([layers[0]["values"]["pH"], layers[1]["values"]["pH"]], [5.2, 6.5])
	assert_eq([layers[0]["dominant_acceptor"], layers[1]["dominant_acceptor"]], ["NO3", "O2"])
	assert_eq(layers[0]["values"].size(), 13, "the 13 bars; organic carbon comes from the pools")


func test_panel_is_named_refreshes_in_place_and_closes_without_its_patch() -> void:
	var ctrl := ControllerRef.new()
	var ui := CanvasLayer.new()
	add_child_autofree(ui)
	var tile := {"field_id": "f", "patch_idx": 0}
	assert_true(ctrl.show_panel({"f": [{"soil_state": _soil([25.0], 1.0)}]}, tile, ui, _bar(ui)))
	var panel: PanelContainer = ctrl._nutrient_panel
	assert_eq(panel.name, "SoilAnalysisPanel")
	assert_true(ctrl.show_panel({"f": [{"soil_state": _soil([25.0], 2.0)}]}, tile, ui, _bar(ui)))
	assert_same(ctrl._nutrient_panel, panel, "refreshed in place, not rebuilt")
	assert_eq(ui.find_children(ControllerRef.PANEL_NAME, "", false, false).size(), 1)
	# A payload without the tile's patch, or without its soil, closes the panel.
	assert_false(ctrl.show_panel({"f": []}, tile, ui, _bar(ui)))
	assert_false(ctrl.is_open())
	assert_false(ctrl.show_panel({"f": [{"events": []}]}, tile, ui, _bar(ui)))
	assert_false(ctrl.is_open())


func test_top_of_a_bottom_bar_reads_its_minimum_before_it_grows() -> void:
	var ui := CanvasLayer.new()
	add_child_autofree(ui)
	var bar := _bar(ui)
	assert_eq(ControllerRef.top_of(bar), 654.0)
	# Anchored to the bottom, it grows up to this on the next frame.
	bar.custom_minimum_size.y = 87.0
	assert_eq(ControllerRef.top_of(bar), 633.0)
