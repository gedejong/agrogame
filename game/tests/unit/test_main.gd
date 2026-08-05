extends GutTest
## Unit tests for Main scene — verifies UI structure.

var _scene: PackedScene


func before_all() -> void:
	_scene = load("res://scenes/main.tscn")


func test_main_scene_loads() -> void:
	assert_not_null(_scene, "Main scene should load")


func test_main_has_new_game_button() -> void:
	var instance = _scene.instantiate()
	var button = instance.find_child("NewGameButton")
	assert_not_null(button, "Main scene should have NewGameButton")
	instance.free()


func test_main_has_status_label() -> void:
	var instance = _scene.instantiate()
	var label = instance.find_child("StatusLabel")
	assert_not_null(label, "Main scene should have StatusLabel")
	instance.free()


func test_main_has_scenario_picker() -> void:
	# The scenario picker (#440) lets the player choose crop/climate/soil at start.
	var instance = _scene.instantiate()
	var picker = instance.find_child("ScenarioPicker")
	assert_not_null(picker, "Main scene should have a ScenarioPicker OptionButton")
	assert_true(picker is OptionButton, "ScenarioPicker should be an OptionButton")
	instance.free()


func test_main_exposes_scenario_helpers() -> void:
	# main.gd wires the picker selection into create_game via these helpers.
	var instance = _scene.instantiate()
	assert_true(instance.has_method("_populate_scenarios"), "main should populate scenarios")
	assert_true(instance.has_method("_selected_patches"), "main should resolve selected patches")
	instance.free()
