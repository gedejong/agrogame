extends Node
## Global autoload singleton for persisting game_id across scene changes.
## Cleared on _ready so a fresh game is created each launch.

var game_id: String = ""


func _ready() -> void:
	game_id = ""
