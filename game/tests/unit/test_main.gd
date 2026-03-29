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
