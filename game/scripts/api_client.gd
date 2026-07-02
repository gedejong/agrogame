extends Node
## HTTP client for communicating with the FastAPI backend.
## Configured for local development at localhost:8000.

const BASE_URL := "http://localhost:8000/api/v1"

var _http_request: HTTPRequest
var _season_request: HTTPRequest
var _step_request: HTTPRequest
var _action_request: HTTPRequest
var _preview_request: HTTPRequest
var _forecast_request: HTTPRequest
var _report_request: HTTPRequest
var _callback: Callable
var _season_callback: Callable
var _step_callback: Callable
var _action_callback: Callable
var _preview_callback: Callable
var _forecast_callback: Callable
var _report_callback: Callable


func _ready() -> void:
	_http_request = HTTPRequest.new()
	add_child(_http_request)
	_http_request.request_completed.connect(_on_request_completed)
	_season_request = HTTPRequest.new()
	add_child(_season_request)
	_season_request.request_completed.connect(_on_season_completed)
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


func create_game(callback: Callable) -> void:
	_callback = callback
	var body := JSON.stringify(
		{
			"fields":
			[
				{
					"field_id": "field_1",
					"patches":
					[
						{
							"soil_profile_key": "sandy_temperate",
							"crop_key": "maize",
							"climate_key": "netherlands_temperate",
							"area_fraction": 0.333
						},
						{
							"soil_profile_key": "loam_temperate",
							"crop_key": "maize",
							"climate_key": "netherlands_temperate",
							"area_fraction": 0.334
						},
						{
							"soil_profile_key": "clay_temperate",
							"crop_key": "maize",
							"climate_key": "netherlands_temperate",
							"area_fraction": 0.333
						}
					]
				}
			],
			"starting_credits": 10000
		}
	)
	var headers := ["Content-Type: application/json"]
	_http_request.request(BASE_URL + "/games", headers, HTTPClient.METHOD_POST, body)


func _on_request_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_callback, result, response_code, body)


func start_season(game_id: String, callback: Callable) -> void:
	_season_callback = callback
	(
		_season_request
		. request(
			BASE_URL + "/games/" + game_id + "/start-season?days=150&seed=42",
			["Content-Type: application/json"],
			HTTPClient.METHOD_POST,
			"",
		)
	)


func _on_season_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_season_callback, result, response_code, body)


func step_day(game_id: String, days: int, callback: Callable) -> void:
	_step_callback = callback
	var url := BASE_URL + "/games/" + game_id + "/step?days=" + str(days)
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
	_preview_callback = callback
	var req := {"field_id": "field_1", "action": action, "params": params}
	var body_str := JSON.stringify(req)
	(
		_preview_request
		. request(
			BASE_URL + "/games/" + game_id + "/action/preview",
			["Content-Type: application/json"],
			HTTPClient.METHOD_POST,
			body_str,
		)
	)


func _on_preview_completed(
	result: int, response_code: int, _headers: PackedStringArray, body: PackedByteArray
) -> void:
	_dispatch_callback(_preview_callback, result, response_code, body)


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
