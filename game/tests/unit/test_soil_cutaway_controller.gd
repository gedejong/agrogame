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
