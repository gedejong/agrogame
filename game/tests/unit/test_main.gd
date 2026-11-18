extends GutTest
## Unit tests for Main scene — verifies UI structure.

var _scene: PackedScene


## Records create_game and answers at once, so the hand-off needs no backend.
class CreateStub:
	extends Node
	var fields: Array = []
	var ok: bool = true

	func create_game(callback: Callable, fields_arg: Array = []) -> void:
		fields = fields_arg
		callback.call(ok, {"game_id": "g-sahel"} if ok else {})


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
	assert_true(instance.has_method("_selected_fields"), "main should resolve selected fields")
	instance.free()


## Main in the tree with skip_menu off, a stub client and a recording scene changer.
func _ready_main(stub: CreateStub, changes: Array) -> Control:
	var skip: bool = ProjectSettings.get_setting("agrogame/debug/skip_menu", false)
	ProjectSettings.set_setting("agrogame/debug/skip_menu", false)
	var main: Control = _scene.instantiate()
	add_child_autofree(main)
	ProjectSettings.set_setting("agrogame/debug/skip_menu", skip)
	add_child_autofree(stub)
	main.api_client = stub
	main._change_scene = func(path: String) -> void: changes.append([path, GameState.game_id])
	return main


func test_new_game_hands_scenario_game_to_farm_view() -> void:
	# #516: the chosen scenario's game id must reach the farm view.
	var stub := CreateStub.new()
	var changes: Array = []
	var main := _ready_main(stub, changes)
	main.scenario_picker.selected = 2  # Sahel sorghum
	main._on_new_game_pressed()
	assert_eq(stub.fields, ScenarioCatalog.fields_for(2), "Sahel fields sent (#548)")
	assert_eq(changes, [["res://scenes/farm_view.tscn", "g-sahel"]], "id stored before the change")
	GameState.game_id = ""


func test_failed_creation_stays_on_title() -> void:
	var stub := CreateStub.new()
	stub.ok = false
	var changes: Array = []
	var main := _ready_main(stub, changes)
	main._on_new_game_pressed()
	assert_eq(changes, [], "no scene change")
	assert_eq(GameState.game_id, "", "nothing handed over")
	assert_string_contains(main.status_label.text, "could not reach backend")
