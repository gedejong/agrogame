extends GutTest
## Unit tests for ApiClient — verifies construction and configuration.

const ApiClientScript = preload("res://scripts/api_client.gd")


func test_base_url_points_to_localhost() -> void:
	assert_eq(
		ApiClientScript.BASE_URL,
		"http://localhost:8000/api/v1",
		"API base URL should point to local FastAPI server",
	)


func test_instantiation_succeeds() -> void:
	var client = ApiClientScript.new()
	assert_not_null(client, "ApiClient should instantiate")
	client.free()


func test_has_create_game_method() -> void:
	var client = ApiClientScript.new()
	assert_true(client.has_method("create_game"), "ApiClient should expose create_game()")
	client.free()


func test_has_preview_action_method() -> void:
	var client = ApiClientScript.new()
	assert_true(
		client.has_method("preview_action"),
		"ApiClient should expose preview_action() for cost preview (#318)",
	)
	client.free()


func test_create_game_accepts_scenario_patches() -> void:
	# create_game(callback, patches := []) drives the chosen scenario (#440);
	# the optional patches arg keeps quick-start backward compatible.
	var client = ApiClientScript.new()
	var args: Array = []
	for method in client.get_method_list():
		if method["name"] == "create_game":
			args = method["args"]
	assert_eq(args.size(), 2, "create_game should accept (callback, patches)")
	client.free()


## ApiClient with the two HTTP calls stubbed, to test Run Season's sequencing
## (#487) without a backend.
class SeasonStubClient:
	extends "res://scripts/api_client.gd"
	var calls: Array = []
	var setup_ok: bool = true
	var season_days: int = 150

	func start_season(game_id: String, callback: Callable) -> void:
		calls.append(["start_season", game_id])
		callback.call(setup_ok, {"season_days": season_days, "day_number": 0})

	func step_day(game_id: String, days: int, callback: Callable) -> void:
		calls.append(["step_day", game_id, days])
		callback.call(true, {"day_number": days, "season_complete": true})


func test_run_season_sets_up_then_steps_every_day() -> void:
	var api := SeasonStubClient.new()
	var results: Array = []
	api.run_season("g1", func(ok: bool, data: Dictionary) -> void: results.append([ok, data]))
	assert_eq(api.calls, [["start_season", "g1"], ["step_day", "g1", 150]])
	assert_eq(results.size(), 1, "callback fires once, with the final /step result")
	assert_true(results[0][0])
	assert_true(results[0][1]["season_complete"])
	api.free()


func test_run_season_steps_the_generated_length() -> void:
	var api := SeasonStubClient.new()
	api.season_days = 60
	api.run_season("g1", func(_ok: bool, _data: Dictionary) -> void: pass)
	assert_eq(api.calls[1], ["step_day", "g1", 60])
	api.free()


func test_run_season_failed_setup_does_not_step() -> void:
	var api := SeasonStubClient.new()
	api.setup_ok = false
	var results: Array = []
	api.run_season("g1", func(ok: bool, data: Dictionary) -> void: results.append([ok, data]))
	assert_eq(api.calls, [["start_season", "g1"]], "no /step after a failed setup")
	assert_eq(results, [[false, {}]])
	api.free()
