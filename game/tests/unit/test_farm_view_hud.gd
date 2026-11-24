extends GutTest
## The HUD shows what the server holds (#582): the credits label carries no
## placeholder, and the Quick Status card is rebuilt from the selected tile
## whenever a step, an action reply or a reconcile changes it. Kept apart from
## test_farm_view.gd, which is at gdlint's public-method cap.

const FarmViewScene = preload("res://scenes/farm_view.tscn")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")

var _auto_cutaway: bool


func before_each() -> void:
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)
	GameState.game_id = ""


## A view on game "g" with no hand-over, tile (0, 0) selected and carrying maize.
func _view() -> Node3D:
	GameState.game_id = ""
	var api := ApiClientTest.StubClient.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._game_id = "g"
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 2
	view._select_tile(0, 0)
	return view


func _header(view: Node3D) -> String:
	return view._quick_status._tile_label.text


func _game(balance: int, crop: String) -> Dictionary:
	var patch := {"soil_profile_key": "loam", "crop_key": crop, "area_fraction": 1.0}
	return {"game_id": "g", "balance_credits": balance, "fields": {"field_1": [patch]}}


func test_credits_show_no_placeholder_before_the_balance_is_known() -> void:
	var view := _view()
	assert_eq(view.credits_label.text, "—", "neutral, not a fake 10000")


func test_the_loaded_games_balance_is_shown_on_load() -> void:
	var view := _view()
	view._on_game_loaded(true, _game(9799, "maize"))
	assert_eq(view.credits_label.text, "9799", "the server's balance")
	assert_eq(view._balance_credits, 9799, "and the pickers' balance")


func test_a_load_without_a_balance_keeps_the_neutral_label() -> void:
	var view := _view()
	view._on_game_loaded(true, {"fields": {"field_1": [{"soil_profile_key": "loam"}]}})
	assert_eq(view.credits_label.text, "—", "no balance, no number")


func test_the_card_follows_a_harvest_over_two_seasons() -> void:
	var view := _view()
	for season in range(2):
		view._tile_data[0]["crop_key"] = "maize"
		view._tile_data[0]["crop_stage"] = 3
		view._select_tile(0, 0)
		assert_true(_header(view).begins_with("Maize"), "season %d: standing crop" % season)
		view._on_harvest_complete(true, {"balance_credits": 1300}, "maize", "field_1", 0)
		assert_true(_header(view).begins_with("Empty"), "season %d: bare after harvest" % season)


func test_the_card_follows_a_reconcile_that_clears_or_sows_the_tile() -> void:
	var view := _view()
	var releases: int = view._releases
	view._on_reconciled(true, _game(1300, ""), "Harvest failed", releases)
	assert_true(_header(view).begins_with("Empty"), "the server harvested it")
	view._on_reconciled(true, _game(1233, "sorghum"), "Plant failed", releases)
	assert_true(_header(view).begins_with("Sorghum"), "the server planted sorghum")


func test_the_card_follows_a_plant_reply() -> void:
	var view := _view()
	view._on_plant_complete(true, {"balance_credits": 900}, "rice", "field_1", 0)
	assert_true(_header(view).begins_with("Rice"), "the planted crop")


func test_the_card_follows_a_step() -> void:
	var view := _view()
	var patch := {"crop_key": "maize", "crop_stage": "vegetative", "lai": 1.0}
	view._apply_patch_data({"field_1": [patch, patch, patch]})
	var before: String = view._quick_status._recommendation_label.text
	patch = {"crop_key": "", "crop_stage": "", "lai": 0.0}
	view._apply_patch_data({"field_1": [patch, patch, patch]})
	assert_true(_header(view).begins_with("Empty"), "the step cleared the crop")
	assert_ne(view._quick_status._recommendation_label.text, before, "and the advice follows")


func test_nothing_is_built_when_no_tile_is_selected() -> void:
	var view := _view()
	view._deselect()
	view._on_reconciled(true, _game(1300, ""), "Harvest failed", view._releases)
	assert_null(view._quick_status, "no card without a selection")
