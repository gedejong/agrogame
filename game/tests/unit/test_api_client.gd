extends GutTest
## Unit tests for ApiClient — verifies construction and configuration.

const ApiClientScript = preload("res://scripts/api_client.gd")
## The six endpoints #534 puts on the queue besides the previews.
const _ENDPOINTS: Array[String] = ["create", "game", "step", "action", "forecast", "report"]


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


## ApiClient with every endpoint's transport stubbed (#534). `_send` records
## each send instead of making it, and `reply` answers an endpoint's send in
## flight as its HTTPRequest's request_completed signal would. Everything
## between the two is the real client, queues included. test_farm_view.gd
## drives the farm view through it as well.
class StubClient:
	extends "res://scripts/api_client.gd"
	## Every send, in order, as [endpoint, url, method, body].
	var sends: Array = []
	## Sends to an endpoint made while its previous send still awaited a reply.
	var busy_sends: int = 0
	## /step or /action sends made while a /step or /action awaited a reply.
	var mutating_overlaps: int = 0
	## Per endpoint, return values for its next sends, consumed in order; OK
	## once exhausted.
	var send_errors_for: Dictionary = {}
	var _awaiting_on: Dictionary = {}

	func _send(endpoint: String, url: String, method: HTTPClient.Method, body: String) -> Error:
		sends.append([endpoint, url, method, body])
		if _awaiting_on.has(endpoint):
			busy_sends += 1
		var mutating_awaited: bool = _awaiting_on.has("step") or _awaiting_on.has("action")
		if endpoint in ["step", "action"] and mutating_awaited:
			mutating_overlaps += 1
		var errors: Array = send_errors_for.get(endpoint, [])
		var err: Error = OK if errors.is_empty() else errors.pop_front()
		if err == OK:
			_awaiting_on[endpoint] = true
		return err

	## Whether `endpoint` has a send awaiting its reply.
	func awaiting(endpoint: String) -> bool:
		return _awaiting_on.has(endpoint)

	## Answer `endpoint`'s send in flight with an HTTP 200 carrying `data`.
	func reply_ok(endpoint: String, data: Dictionary) -> void:
		reply(endpoint, HTTPRequest.RESULT_SUCCESS, 200, JSON.stringify(data))

	## Answer `endpoint`'s send in flight with any result, status and body.
	func reply(endpoint: String, result: int, response_code: int, body: String) -> void:
		_awaiting_on.erase(endpoint)
		_on_completed(result, response_code, PackedStringArray(), body.to_utf8_buffer(), endpoint)


## ApiClient with the step transport stubbed (#537). `_send` records each step
## URL instead of sending it, and `respond` answers it through `_on_completed`,
## as the HTTPRequest's request_completed signal would.
class StepStubClient:
	extends StubClient
	var sent: Array = []

	func _send(endpoint: String, url: String, method: HTTPClient.Method, body: String) -> Error:
		if endpoint == "step":
			sent.append(url)
		return super(endpoint, url, method, body)

	func respond(result: int, response_code: int, body: String) -> void:
		reply("step", result, response_code, body)


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


## ApiClient with the cost-preview transport stubbed (#523). `_send` records
## each preview instead of sending it, and `respond` delivers the response
## through `_on_completed`, as the HTTPRequest's request_completed signal would.
## Everything between the two is the real client; other endpoints are stubbed
## as in StubClient. test_farm_view.gd drives the farm view through it as well.
class PreviewStubClient:
	extends StubClient
	## Every preview sent, in order, as [action, params].
	var sent: Array = []
	## Sends made while an earlier one was still awaiting its response.
	var overlapping_sends: int = 0
	## Return values for the next sends, consumed in order; OK once exhausted.
	var send_errors: Array = []
	var _awaiting: bool = false

	func _send(endpoint: String, url: String, method: HTTPClient.Method, body: String) -> Error:
		if endpoint != "preview":
			return super(endpoint, url, method, body)
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
		_on_completed(result, response_code, PackedStringArray(), body.to_utf8_buffer(), "preview")


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
	var client := _stub_client()
	var got: Array = []
	for _i in range(3):
		client.get_game("g", func(ok: bool, data: Dictionary) -> void: got.append([ok, data]))
	var body := JSON.stringify({"game_id": "g"})
	client.reply("game", HTTPRequest.RESULT_SUCCESS, 404, "")
	client.reply("game", HTTPRequest.RESULT_CANT_CONNECT, 0, "")
	client.reply("game", HTTPRequest.RESULT_SUCCESS, 200, body)
	assert_eq(got, [[false, {"not_found": true}], [false, {}], [true, {"game_id": "g"}]])


func _stub_client() -> StubClient:
	var api: StubClient = StubClient.new()
	add_child_autofree(api)
	return api


## Call `endpoint` once per tag, in order, each with a recorder for its tag.
func _call_each(api: StubClient, endpoint: String, got: Array, tags: Array) -> void:
	for tag: String in tags:
		var callback := _recorder(got, tag)
		match endpoint:
			"create":
				api.create_game(callback)
			"game":
				api.get_game("g", callback)
			"step":
				api.step_day("g", 1, callback)
			"action":
				api.execute_action("g", "irrigate", {}, callback)
			"forecast":
				api.get_forecast("g", callback)
			"report":
				api.get_report("g", callback)


func test_each_call_gets_its_own_reply_once_in_call_order() -> void:
	# #534 AC2: a second call made before the first reply took over the stored
	# callback and was never sent (ERR_BUSY), so the first reply reached the
	# second caller and the first caller never heard back.
	for endpoint: String in _ENDPOINTS:
		var api := _stub_client()
		var got: Array = []
		_call_each(api, endpoint, got, ["first", "second"])
		assert_eq(api.sends.size(), 1, "%s: the second call waits for the first" % endpoint)
		api.reply_ok(endpoint, {"n": "1"})
		assert_eq(got, [["first", true, {"n": "1"}]], "%s: first reply, first caller" % endpoint)
		api.reply_ok(endpoint, {"n": "2"})
		var both := [["first", true, {"n": "1"}], ["second", true, {"n": "2"}]]
		assert_eq(got, both, "%s: each its own reply, once, in order" % endpoint)
		assert_eq(api.sends.size(), 2, "%s: both sent" % endpoint)
		assert_eq(api.busy_sends, 0, "%s: no send while one is in flight" % endpoint)


func test_a_rejected_send_fails_only_its_own_call() -> void:
	# #534 AC2: a send request() rejects fails its own call at once, and the
	# next call is still sent and answered.
	for endpoint: String in _ENDPOINTS:
		var api := _stub_client()
		api.send_errors_for[endpoint] = [OK, ERR_CANT_CONNECT]
		var got: Array = []
		_call_each(api, endpoint, got, ["first", "second", "third"])
		api.reply_ok(endpoint, {"n": "1"})
		var two := [["first", true, {"n": "1"}], ["second", false, {}]]
		assert_eq(got, two, "%s: the second failed on send" % endpoint)
		api.reply_ok(endpoint, {"n": "3"})
		assert_eq(
			got.slice(2), [["third", true, {"n": "3"}]], "%s: the third still sent" % endpoint
		)
		assert_eq(api.sends.size(), 3, "%s: three sends" % endpoint)


func test_a_failed_reply_fails_only_its_own_call() -> void:
	# #534 AC2: a transport error, a non-200 and an unparsable body each fail
	# their own call, and the next call is still sent and answered.
	var failures: Array = [
		[HTTPRequest.RESULT_CANT_CONNECT, 0, ""],
		[HTTPRequest.RESULT_SUCCESS, 500, "{}"],
		[HTTPRequest.RESULT_SUCCESS, 200, "not json"],
	]
	for endpoint: String in _ENDPOINTS:
		for failure: Array in failures:
			var api := _stub_client()
			var got: Array = []
			_call_each(api, endpoint, got, ["first", "second"])
			api.reply(endpoint, failure[0], failure[1], failure[2])
			api.reply_ok(endpoint, {"n": "2"})
			var want := [["first", false, {}], ["second", true, {"n": "2"}]]
			assert_eq(got, want, "%s, failure %s" % [endpoint, failure])


func test_each_endpoint_sends_its_request_on_its_own_http_request() -> void:
	# #534 AC1: one HTTPRequest per endpoint, so a call in flight on one never
	# holds up another, and each call sends the request it sent before the queue.
	var api := _stub_client()
	var ignore := func(_ok: bool, _data: Dictionary) -> void: pass
	api.create_game(ignore)
	api.get_game("g", ignore)
	api.step_day("g", 3, ignore)
	api.execute_action("g", "irrigate", {"amount_mm": 20}, ignore)
	api.preview_action("g", "tillage", {"intensity": 0.8}, ignore)
	api.get_forecast("g", ignore)
	api.get_report("g", ignore)
	var games := ApiClientScript.BASE_URL + "/games"
	var post := HTTPClient.METHOD_POST
	var fetch := HTTPClient.METHOD_GET
	var expected := [
		["create", games, post],
		["game", games + "/g", fetch],
		["step", games + "/g/step?days=3", post],
		["action", games + "/g/action", post],
		["preview", games + "/g/action/preview", post],
		["forecast", games + "/g/forecast", fetch],
		["report", games + "/g/report", fetch],
	]
	assert_eq(api.sends.map(func(s: Array) -> Array: return s.slice(0, 3)), expected)
	var bodies: Array = api.sends.map(func(s: Array) -> String: return s[3])
	var create: Dictionary = JSON.parse_string(bodies[0])
	assert_eq(create["fields"][0]["field_id"], "field_1", "the default scenario's field")
	assert_eq(create["fields"][0]["patches"].size(), ScenarioCatalog.default_patches().size())
	var action := {"field_id": "field_1", "action": "irrigate", "params": {"amount_mm": 20}}
	var preview := {"field_id": "field_1", "action": "tillage", "params": {"intensity": 0.8}}
	assert_eq(bodies.slice(3, 5), [JSON.stringify(action), JSON.stringify(preview)])
	assert_eq([bodies[1], bodies[2], bodies[5], bodies[6]], ["", "", "", ""], "no body")
	assert_eq(api.get_children().size(), 7, "one HTTPRequest per endpoint")
