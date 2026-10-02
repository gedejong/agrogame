extends GutTest
## Tests for SoilCutawayController.

const ControllerRef = preload("res://scripts/soil_cutaway_controller.gd")


func test_new_controller_not_active() -> void:
	var ctrl := ControllerRef.new()
	assert_false(ctrl.is_active())


func test_is_valid_within_bounds() -> void:
	assert_true(ControllerRef._is_valid(Vector2i(0, 0), 6, 6))
	assert_true(ControllerRef._is_valid(Vector2i(5, 5), 6, 6))


func test_is_valid_out_of_bounds() -> void:
	assert_false(ControllerRef._is_valid(Vector2i(-1, 0), 6, 6))
	assert_false(ControllerRef._is_valid(Vector2i(6, 0), 6, 6))
	assert_false(ControllerRef._is_valid(Vector2i(0, 6), 6, 6))


func test_hide_tile_info_no_crash_when_empty() -> void:
	var ctrl := ControllerRef.new()
	ctrl.hide_tile_info()
	assert_false(ctrl.is_active())


func test_hide_nutrient_panel_no_crash_when_empty() -> void:
	var ctrl := ControllerRef.new()
	ctrl.hide_nutrient_panel()
	assert_false(ctrl.is_active())


func test_inspector_wires_each_layers_three_carbon_pools() -> void:
	var previous_unit: Variant = ProjectSettings.get_setting("agrogame/display/mass_unit")
	ProjectSettings.set_setting("agrogame/display/mass_unit", UiTheme.MASS_UNIT_GM2)
	var ctrl := ControllerRef.new()
	var ui := CanvasLayer.new()
	add_child_autofree(ui)
	var columns: Array[Dictionary] = [
		{
			"show_info": false,
			"profile": [{"depth_cm": 30}],
			"soil_state": {"som_labile_c": [99999.0]},
		},
		{
			"show_info": true,
			"profile": [{"depth_cm": 30}, {"depth_cm": 40}],
			"soil_state":
			{
				"som_labile_c": [100.0, 10.0],
				"som_intermediate_c": [200.0, 20.0],
				"som_stable_c": [700.0, 70.0],
			},
		},
	]
	ctrl._show_nutrient_panel(columns, ui)
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
