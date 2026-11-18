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


## ApiClient with the step transport stubbed (#537). `_send_step` records each
## URL instead of sending it, and `respond` answers it by calling
## `_on_step_completed`, as the HTTPRequest's request_completed signal would.
class StepStubClient:
	extends "res://scripts/api_client.gd"
	var sent: Array = []

	func _send_step(url: String) -> void:
		sent.append(url)

	func respond(result: int, response_code: int, body: String) -> void:
		_on_step_completed(result, response_code, PackedStringArray(), body.to_utf8_buffer())


func test_run_season_sends_only_one_step_for_the_window() -> void:
	# #537: each Run is exactly POST /step?days=200; no /start-season, no stop_on_pause.
	var api: StepStubClient = StepStubClient.new()
	add_child_autofree(api)
	var got: Array = []
	var record := func(ok: bool, data: Dictionary) -> void: got.append([ok, data])
	api.run_season("g1", record)
	api.respond(HTTPRequest.RESULT_SUCCESS, 200, JSON.stringify({"season_complete": true}))
	api.run_season("g1", record)  # a second Run, once the window has ended
	api.respond(HTTPRequest.RESULT_CANT_CONNECT, 0, "")
	var url: String = ApiClientScript.BASE_URL + "/games/g1/step?days=200"
	assert_eq(api.sent, [url, url], "one /step per Run")
	for http: HTTPRequest in api.get_children():
		assert_eq(
			http.get_http_client_status(), HTTPClient.STATUS_DISCONNECTED, "nothing else sent"
		)
	assert_eq(
		got, [[true, {"season_complete": true}], [false, {}]], "each Run gets its /step result"
	)
	assert_false(api.has_method("start_season"), "start_season is gone")
	assert_false("_season_request" in api, "_season_request is gone")


## ApiClient with the cost-preview transport stubbed (#523). `_send_preview`
## records each request instead of sending it, and `respond` delivers the
## response by calling `_on_preview_completed`, as the HTTPRequest's
## request_completed signal would. Everything between the two is the real client.
## test_farm_view.gd drives the farm view through it as well.
class PreviewStubClient:
	extends "res://scripts/api_client.gd"
	## Every preview sent, in order, as [action, params].
	var sent: Array = []
	## Sends made while an earlier one was still awaiting its response.
	var overlapping_sends: int = 0
	## Return values for the next sends, consumed in order; OK once exhausted.
	var send_errors: Array = []
	var _awaiting: bool = false

	func _send_preview(_url: String, body: String) -> Error:
		var req: Dictionary = JSON.parse_string(body)
		sent.append([req["action"], req["params"]])
		if _awaiting:
			overlapping_sends += 1
		var err: Error = OK if send_errors.is_empty() else send_errors.pop_front()
		_awaiting = err == OK
		return err

	## Answer the preview in flight with an HTTP 200 carrying `data`.
	func resolve(data: Dictionary) -> void:
		respond(HTTPRequest.RESULT_SUCCESS, 200, JSON.stringify(data))

	## Answer the preview in flight with an arbitrary result, status and body.
	func respond(result: int, response_code: int, body: String) -> void:
		_awaiting = false
		_on_preview_completed(result, response_code, PackedStringArray(), body.to_utf8_buffer())


func _preview_client() -> PreviewStubClient:
	var api: PreviewStubClient = PreviewStubClient.new()
	add_child_autofree(api)
	return api


## A preview callback that appends [tag, ok, data] to `got`.
func _recorder(got: Array, tag: String) -> Callable:
	return func(ok: bool, data: Dictionary) -> void: got.append([tag, ok, data])


func _queue_previews(api: PreviewStubClient, got: Array, actions: Array) -> void:
	for action: String in actions:
		api.preview_action("g", action, {}, _recorder(got, action))


func test_back_to_back_previews_reach_their_own_callbacks() -> void:
	# #523 AC5(a): a second preview made while the first is in flight used to
	# take over its callback, so irrigate's price landed on Fertilize's handler.
	var api := _preview_client()
	var got: Array = []
	_queue_previews(api, got, ["irrigate", "fertilize"])
	api.resolve({"action": "irrigate"})
	assert_eq(got, [["irrigate", true, {"action": "irrigate"}]], "first reply, first callback")
	api.resolve({"action": "fertilize"})
	assert_eq(
		got,
		[["irrigate", true, {"action": "irrigate"}], ["fertilize", true, {"action": "fertilize"}]],
		"each reply reaches its own callback, in order, once",
	)


func test_previews_are_sent_one_at_a_time_in_call_order() -> void:
	# #523 AC5(b): never a send while one is in flight (that is the ERR_BUSY path).
	var api := _preview_client()
	_queue_previews(api, [], ["irrigate", "fertilize", "tillage"])
	assert_eq(api.sent, [["irrigate", {}]], "the others wait for the first")
	api.resolve({})
	api.resolve({})
	api.resolve({})
	assert_eq(api.sent, [["irrigate", {}], ["fertilize", {}], ["tillage", {}]], "FIFO")
	assert_eq(api.overlapping_sends, 0, "no send while one is in flight")


func test_a_failed_send_fails_only_its_own_preview() -> void:
	# #523 AC5(c)/AC4: a send that request() rejects fails at once and the queue moves on.
	var api := _preview_client()
	api.send_errors = [OK, ERR_CANT_CONNECT]
	var got: Array = []
	_queue_previews(api, got, ["irrigate", "fertilize", "tillage"])
	api.resolve({"action": "irrigate"})
	assert_eq(got.slice(1), [["fertilize", false, {}]], "fertilize failed on send")
	assert_eq(api.sent.size(), 3, "tillage was sent next")
	api.resolve({"action": "tillage"})
	assert_eq(got.map(func(g: Array) -> String: return g[0]), ["irrigate", "fertilize", "tillage"])
	assert_eq(got[2], ["tillage", true, {"action": "tillage"}])


func test_a_failed_response_fails_only_its_own_preview() -> void:
	# #523 AC5(c)/AC4: transport error, non-200 and unparsable body each fail
	# their own preview, and the next one is still sent and answered.
	var failures: Array = [
		[HTTPRequest.RESULT_CANT_CONNECT, 0, ""],
		[HTTPRequest.RESULT_SUCCESS, 500, "{}"],
		[HTTPRequest.RESULT_SUCCESS, 200, "not json"],
	]
	for failure: Array in failures:
		var api := _preview_client()
		var got: Array = []
		_queue_previews(api, got, ["irrigate", "fertilize"])
		api.respond(failure[0], failure[1], failure[2])
		api.resolve({"action": "fertilize"})
		assert_eq(
			got,
			[["irrigate", false, {}], ["fertilize", true, {"action": "fertilize"}]],
			"failure %s" % [failure],
		)


func test_preview_reply_with_nothing_in_flight_is_reported() -> void:
	var api := _preview_client()
	api.resolve({})
	assert_push_error("no preview in flight")


func test_get_game_tells_not_found_from_unreachable() -> void:
	# #516: a 404 means the backend lost the game; the farm view returns to the title.
	var client = ApiClientScript.new()
	var got: Array = []
	client._game_callback = func(ok: bool, data: Dictionary) -> void: got.append([ok, data])
	var none := PackedByteArray()
	var body := JSON.stringify({"game_id": "g"}).to_utf8_buffer()
	client._on_game_completed(HTTPRequest.RESULT_SUCCESS, 404, PackedStringArray(), none)
	client._on_game_completed(HTTPRequest.RESULT_CANT_CONNECT, 0, PackedStringArray(), none)
	client._on_game_completed(HTTPRequest.RESULT_SUCCESS, 200, PackedStringArray(), body)
	assert_eq(got, [[false, {"not_found": true}], [false, {}], [true, {"game_id": "g"}]])
	client.free()
