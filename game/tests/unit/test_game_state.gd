extends GutTest
## Tests for the GameState global singleton.

const GameStateScript = preload("res://scripts/game_state.gd")


func test_default_game_id_empty() -> void:
	var state := GameStateScript.new()
	assert_eq(state.game_id, "", "Default game_id should be empty")


func test_game_id_persists() -> void:
	var state := GameStateScript.new()
	state.game_id = "abc123"
	assert_eq(state.game_id, "abc123", "game_id should persist after assignment")
