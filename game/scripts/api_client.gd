extends Node
## HTTP client for communicating with the FastAPI backend.
## Configured for local development at localhost:8000.

const BASE_URL := "http://localhost:8000/api/v1"
## Days one Run Season asks /step for: the backend's weather window
## (DEFAULT_SEASON_DAYS, agrogame/api/state.py), so a Run ends at the window's
## end from any day (#537). /step returns a snapshot per day, so this also caps
## the response size (#531).
const RUN_SEASON_DAYS := 200

## Every endpoint has its own HTTPRequest, which takes one request at a time,
## so its calls wait in a FIFO queue as {url, method, body, callback} and go out
## one at a time (#523, generalised in #534). Each callback stays bound to its
## own entry, so a reply can only reach the call that made it. Endpoints do not
## wait on each other.
const _ENDPOINTS: Array[String] = [
	"create", "game", "step", "action", "preview", "forecast", "report"
]

var _requests: Dictionary = {}  # endpoint -> its HTTPRequest
var _queues: Dictionary = {}  # endpoint -> Array of waiting entries
var _in_flight: Dictionary = {}  # endpoint -> the entry sent; no key when idle


func _ready() -> void:
	for endpoint: String in _ENDPOINTS:
		var http := HTTPRequest.new()
		if endpoint == "step":
			http.download_chunk_size = 65536
		add_child(http)
		http.request_completed.connect(_on_completed.bind(endpoint))
		_requests[endpoint] = http
		_queues[endpoint] = []


func create_game(callback: Callable, patches: Array = []) -> void:
	## Create a game from a scenario's patch configs (issue #440). An empty
	## `patches` falls back to the curated default scenario, so quick-start /
	## skip_menu behaviour is unchanged.
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
	_enqueue("create", BASE_URL + "/games", HTTPClient.METHOD_POST, body, callback)


## Run Season (#537): one /step for RUN_SEASON_DAYS, and nothing else. The
## backend clamps it to the days left in the weather window, and rolls a
## finished window over exactly as Next Day does. callback receives the /step
## result, as Next Day's does.
func run_season(game_id: String, callback: Callable) -> void:
	step_day(game_id, RUN_SEASON_DAYS, callback)


func step_day(game_id: String, days: int, callback: Callable) -> void:
	var url := BASE_URL + "/games/" + game_id + "/step?days=" + str(days)
	_enqueue("step", url, HTTPClient.METHOD_POST, "", callback)


func execute_action(
	game_id: String, action: String, params: Dictionary, callback: Callable
) -> void:
	var req := {"field_id": "field_1", "action": action, "params": params}
	var url := BASE_URL + "/games/" + game_id + "/action"
	_enqueue("action", url, HTTPClient.METHOD_POST, JSON.stringify(req), callback)


func preview_action(
	game_id: String, action: String, params: Dictionary, callback: Callable
) -> void:
	## Fetch an action's estimated cost + affordability without executing it (#318).
	var req := {"field_id": "field_1", "action": action, "params": params}
	var url := BASE_URL + "/games/" + game_id + "/action/preview"
	_enqueue("preview", url, HTTPClient.METHOD_POST, JSON.stringify(req), callback)


func get_forecast(game_id: String, callback: Callable) -> void:
	var url := BASE_URL + "/games/" + game_id + "/forecast"
	_enqueue("forecast", url, HTTPClient.METHOD_GET, "", callback)


func get_report(game_id: String, callback: Callable) -> void:
	var url := BASE_URL + "/games/" + game_id + "/report"
	_enqueue("report", url, HTTPClient.METHOD_GET, "", callback)


## Game status plus each field's patch layout (#516). A 404 (the backend has
## lost the game, e.g. after a restart) reports {"not_found": true}, so the
## caller can tell it apart from an unreachable backend.
func get_game(game_id: String, callback: Callable) -> void:
	_enqueue("game", BASE_URL + "/games/" + game_id, HTTPClient.METHOD_GET, "", callback)


func _enqueue(
	endpoint: String, url: String, method: HTTPClient.Method, body: String, callback: Callable
) -> void:
	var queue: Array = _queues[endpoint]
	queue.append({"url": url, "method": method, "body": body, "callback": callback})
	_send_next(endpoint)


## Send the endpoint's oldest waiting call unless one is in flight. A send
## request() rejects fails its own call only, and the queue moves on (#523).
func _send_next(endpoint: String) -> void:
	var queue: Array = _queues[endpoint]
	while not _in_flight.has(endpoint) and not queue.is_empty():
		var entry: Dictionary = queue.pop_front()
		if _send(endpoint, entry["url"], entry["method"], entry["body"]) == OK:
			_in_flight[endpoint] = entry
			return
		var callback: Callable = entry["callback"]
		callback.call(false, {})


## The client's only network call; tests override it to stub the transport.
func _send(endpoint: String, url: String, method: HTTPClient.Method, body: String) -> Error:
	var headers: PackedStringArray = []
	if method == HTTPClient.METHOD_POST:
		headers.append("Content-Type: application/json")
	var http: HTTPRequest = _requests[endpoint]
	return http.request(url, headers, method, body)


## An endpoint's reply. The call leaves the queue before its callback runs, so
## the callback may call the same endpoint again; that call is sent at once.
func _on_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
	endpoint: String,
) -> void:
	if endpoint == "step":
		print("[API] step response: %d bytes, code=%d" % [body.size(), response_code])
	var entry: Dictionary = _in_flight.get(endpoint, {})
	_in_flight.erase(endpoint)
	if entry.is_empty():
		push_error("[API] %s response with no %s in flight" % [endpoint, endpoint])
		return
	var callback: Callable = entry["callback"]
	if endpoint == "game" and result == HTTPRequest.RESULT_SUCCESS and response_code == 404:
		callback.call(false, {"not_found": true})
	else:
		_dispatch_callback(callback, result, response_code, body)
	_send_next(endpoint)


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
