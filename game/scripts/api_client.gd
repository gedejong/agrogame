extends Node
## HTTP client for communicating with the FastAPI backend.
## Configured for local development at localhost:8000.

const BASE_URL := "http://localhost:8000/api/v1"
## Days one Run Season asks /step for: the backend's weather window
## (DEFAULT_SEASON_DAYS, agrogame/api/state.py), so a Run ends at the window's
## end from any day (#537). /step returns a snapshot per day, so this also caps
## the response size (#531).
const RUN_SEASON_DAYS := 200

var _http_request: HTTPRequest
var _step_request: HTTPRequest
var _action_request: HTTPRequest
var _preview_request: HTTPRequest
var _forecast_request: HTTPRequest
var _report_request: HTTPRequest
var _game_request: HTTPRequest
var _callback: Callable
var _step_callback: Callable
var _action_callback: Callable
var _forecast_callback: Callable
var _report_callback: Callable
var _game_callback: Callable
## Previews share _preview_request, which takes one request at a time, so they
## wait here in FIFO order as {url, body, callback} (#523). Each callback stays
## bound to its own entry, so a response can only reach the call that made it.
## Entries are opaque: any action, any params, any number of them.
var _preview_queue: Array[Dictionary] = []
var _preview_in_flight: Dictionary = {}  # the entry sent; empty when idle


func _ready() -> void:
	_http_request = HTTPRequest.new()
	add_child(_http_request)
	_http_request.request_completed.connect(_on_request_completed)
	_step_request = HTTPRequest.new()
	_step_request.download_chunk_size = 65536
	add_child(_step_request)
	_step_request.request_completed.connect(_on_step_completed)
	_action_request = HTTPRequest.new()
	add_child(_action_request)
	_action_request.request_completed.connect(_on_action_completed)
	_preview_request = HTTPRequest.new()
	add_child(_preview_request)
	_preview_request.request_completed.connect(_on_preview_completed)
	_forecast_request = HTTPRequest.new()
	add_child(_forecast_request)
	_forecast_request.request_completed.connect(_on_forecast_completed)


func create_game(callback: Callable, patches: Array = []) -> void:
	## Create a game from a scenario's patch configs (issue #440). An empty
	## `patches` falls back to the curated default scenario, so quick-start /
	## skip_menu behaviour is unchanged.
	_callback = callback
	var game_patches: Array = patches
	if game_patches.is_empty():
		game_patches = ScenarioCatalog.default_patches()
	var body := (
		JSON
		. stringify(
			{
				"fields": [{"field_id": "field_1", "patches": game_patches}],
				"starting_credits": 10000,
			}
		)
	)
	var headers := ["Content-Type: application/json"]
	_http_request.request(BASE_URL + "/games", headers, HTTPClient.METHOD_POST, body)


func _on_request_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_callback, result, response_code, body)


## Run Season (#537): one /step for RUN_SEASON_DAYS, and nothing else. The
## backend clamps it to the days left in the weather window, and rolls a
## finished window over exactly as Next Day does. callback receives the /step
## result, as Next Day's does.
func run_season(game_id: String, callback: Callable) -> void:
	step_day(game_id, RUN_SEASON_DAYS, callback)


func step_day(game_id: String, days: int, callback: Callable) -> void:
	_step_callback = callback
	_send_step(BASE_URL + "/games/" + game_id + "/step?days=" + str(days))


## The step path's only network call; tests override it to stub the transport.
func _send_step(url: String) -> void:
	_step_request.request(url, ["Content-Type: application/json"], HTTPClient.METHOD_POST, "")


func _on_step_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	print("[API] step response: %d bytes, code=%d" % [body.size(), response_code])
	_dispatch_callback(_step_callback, result, response_code, body)


func execute_action(
	game_id: String, action: String, params: Dictionary, callback: Callable
) -> void:
	_action_callback = callback
	var req := {"field_id": "field_1", "action": action, "params": params}
	var body_str := JSON.stringify(req)
	(
		_action_request
		. request(
			BASE_URL + "/games/" + game_id + "/action",
			["Content-Type: application/json"],
			HTTPClient.METHOD_POST,
			body_str,
		)
	)


func _on_action_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_action_callback, result, response_code, body)


func preview_action(
	game_id: String, action: String, params: Dictionary, callback: Callable
) -> void:
	## Fetch an action's estimated cost + affordability without executing it (#318).
	## Queued behind any preview in flight and sent in call order (#523).
	var req := {"field_id": "field_1", "action": action, "params": params}
	var url := BASE_URL + "/games/" + game_id + "/action/preview"
	_preview_queue.append({"url": url, "body": JSON.stringify(req), "callback": callback})
	_send_next_preview()


## Send the oldest waiting preview unless one is in flight. A send request()
## rejects fails its own entry only, and the queue moves on (#523).
func _send_next_preview() -> void:
	while _preview_in_flight.is_empty() and not _preview_queue.is_empty():
		var entry: Dictionary = _preview_queue.pop_front()
		if _send_preview(entry["url"], entry["body"]) == OK:
			_preview_in_flight = entry
			return
		var callback: Callable = entry["callback"]
		callback.call(false, {})


## The preview path's only network call; tests override it to stub the transport.
func _send_preview(url: String, body: String) -> Error:
	return _preview_request.request(
		url, ["Content-Type: application/json"], HTTPClient.METHOD_POST, body
	)


func _on_preview_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	var entry: Dictionary = _preview_in_flight
	_preview_in_flight = {}
	if entry.is_empty():
		push_error("[API] preview response with no preview in flight")
		return
	var callback: Callable = entry["callback"]
	_dispatch_callback(callback, result, response_code, body)
	_send_next_preview()


func get_forecast(game_id: String, callback: Callable) -> void:
	_forecast_callback = callback
	var url := BASE_URL + "/games/" + game_id + "/forecast"
	_forecast_request.request(url, [], HTTPClient.METHOD_GET, "")


func _on_forecast_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_forecast_callback, result, response_code, body)


func get_report(game_id: String, callback: Callable) -> void:
	if not _report_request:
		_report_request = HTTPRequest.new()
		add_child(_report_request)
		_report_request.request_completed.connect(_on_report_completed)
	_report_callback = callback
	var url := BASE_URL + "/games/" + game_id + "/report"
	_report_request.request(url, [], HTTPClient.METHOD_GET, "")


func _on_report_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_report_callback, result, response_code, body)


## Game status plus each field's patch layout (#516). A 404 (the backend has
## lost the game, e.g. after a restart) reports {"not_found": true}, so the
## caller can tell it apart from an unreachable backend.
func get_game(game_id: String, callback: Callable) -> void:
	if not _game_request:
		_game_request = HTTPRequest.new()
		add_child(_game_request)
		_game_request.request_completed.connect(_on_game_completed)
	_game_callback = callback
	_game_request.request(BASE_URL + "/games/" + game_id, [], HTTPClient.METHOD_GET, "")


func _on_game_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	if result == HTTPRequest.RESULT_SUCCESS and response_code == 404:
		_game_callback.call(false, {"not_found": true})
		return
	_dispatch_callback(_game_callback, result, response_code, body)


func _dispatch_callback(
	cb: Callable, result: int, response_code: int, body: PackedByteArray
) -> void:
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		cb.call(false, {})
		return
	var json := JSON.new()
	var parse_result := json.parse(body.get_string_from_utf8())
	if parse_result != OK:
		cb.call(false, {})
		return
	cb.call(true, json.data)
