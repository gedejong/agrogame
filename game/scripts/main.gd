extends Control
## Main menu — minimal connectivity proof for AGRO-113.
## "New Game" button calls POST /api/v1/games via the ApiClient.

var api_client: Node

@onready var new_game_button: Button = $VBoxContainer/NewGameButton
@onready var status_label: Label = $VBoxContainer/StatusLabel
@onready var scenario_picker: OptionButton = $VBoxContainer/ScenarioPicker


func _ready() -> void:
	api_client = preload("res://scripts/api_client.gd").new()
	add_child(api_client)
	_populate_scenarios()
	new_game_button.pressed.connect(_on_new_game_pressed)
	status_label.text = "Ready — backend at localhost:8000"
	if ProjectSettings.get_setting("agrogame/debug/crop_preview", false):
		get_tree().change_scene_to_file("res://scenes/crop_preview.tscn")
		return
	var skip_menu: bool = ProjectSettings.get_setting("agrogame/debug/skip_menu", false)
	if skip_menu:
		_on_new_game_pressed()


## Fill the scenario dropdown from the curated catalog and select the default.
func _populate_scenarios() -> void:
	scenario_picker.clear()
	for i in range(ScenarioCatalog.option_count()):
		scenario_picker.add_item(ScenarioCatalog.label_for(i), i)
	scenario_picker.selected = ScenarioCatalog.DEFAULT_ID


## Patch configs for the currently selected scenario, falling back to the
## default when the selection is somehow out of range.
func _selected_patches() -> Array:
	var option_id: int = scenario_picker.selected
	if not ScenarioCatalog.is_valid(option_id):
		return ScenarioCatalog.default_patches()
	return ScenarioCatalog.patches_for(option_id)


func _on_new_game_pressed() -> void:
	status_label.text = "Creating game..."
	new_game_button.disabled = true
	api_client.create_game(_on_game_created, _selected_patches())


func _on_game_created(success: bool, data: Dictionary) -> void:
	new_game_button.disabled = false
	if success:
		var game_id = data.get("game_id", "unknown")
		status_label.text = "Game created: %s — loading farm..." % game_id
		get_tree().change_scene_to_file("res://scenes/farm_view.tscn")
	else:
		status_label.text = "Error: could not reach backend"
