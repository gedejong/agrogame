extends Control
## Main menu — minimal connectivity proof for AGRO-113.
## "New Game" button calls POST /api/v1/games via the ApiClient.

var api_client: Node

@onready var new_game_button: Button = $VBoxContainer/NewGameButton
@onready var status_label: Label = $VBoxContainer/StatusLabel


func _ready() -> void:
	api_client = preload("res://scripts/api_client.gd").new()
	add_child(api_client)
	new_game_button.pressed.connect(_on_new_game_pressed)
	status_label.text = "Ready — backend at localhost:8000"


func _on_new_game_pressed() -> void:
	status_label.text = "Creating game..."
	new_game_button.disabled = true
	api_client.create_game(_on_game_created)


func _on_game_created(success: bool, data: Dictionary) -> void:
	new_game_button.disabled = false
	if success:
		var game_id = data.get("game_id", "unknown")
		status_label.text = "Game created: %s — loading farm..." % game_id
		var use_3d: bool = ProjectSettings.get_setting("agrogame/rendering/use_3d", false)
		var scene_path := (
			"res://scenes/farm_view_3d.tscn" if use_3d else "res://scenes/farm_view.tscn"
		)
		get_tree().change_scene_to_file(scene_path)
	else:
		status_label.text = "Error: could not reach backend"
