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
## A /step's timeout grows with the days it asks for (#564), so a hung 1-day
## Next Day holds the bar for 10.5 s, not Run Season's allowance.
const STEP_TIMEOUT_BASE_S := 10.0
const STEP_TIMEOUT_PER_DAY_S := 0.5
## Seconds a sent call may await its reply before the client gives up on it
## (#556); without one, a backend that hangs holds the bar #534 keeps disabled
## until a reply is applied. Measured on an M1 Pro: Run Season's 200-day /step
## (16.3 MB, 1.9 s on the backend) took 6.2 s client-side at 60 fps and 14.7 s
## at 20 fps, since HTTPRequest reads one download_chunk_size chunk per frame.
## "step" is the ceiling of 10 s + 0.5 s/day, which Run Season's 200 days reach:
## 110 s leaves 7.5x at 20 fps and 17.7x at 60 fps. No /step steps more, since
## the backend clamps it to the days left in its weather window, 200 for every
## game this client creates. Every other endpoint answered in under 0.1 s, so
## 10 s leaves 100x.
const TIMEOUT_S: Dictionary = {
	"create": 10.0,
	"game": 10.0,
	"step": STEP_TIMEOUT_BASE_S + STEP_TIMEOUT_PER_DAY_S * RUN_SEASON_DAYS,
	"action": 10.0,
	"preview": 10.0,
	"forecast": 10.0,
	"report": 10.0,
}

var _requests: Dictionary = {}  # endpoint -> its HTTPRequest
var _queues: Dictionary = {}  # endpoint -> Array of waiting entries
var _in_flight: Dictionary = {}  # endpoint -> the entry sent; no key when idle
var _sends: int = 0  # successful sends so far; numbers each entry in flight


func _ready() -> void:
	for endpoint: String in _ENDPOINTS:
		var http := HTTPRequest.new()
		if endpoint == "step":
			http.download_chunk_size = 65536
		add_child(http)
		http.request_completed.connect(_on_completed.bind(endpoint))
		_requests[endpoint] = http
		_queues[endpoint] = []


func create_game(callback: Callable, fields: Array = []) -> void:
	## Create a game from a scenario's fields, each {field_id, patches} (#440,
	## #548). An empty `fields` falls back to the curated default scenario, so
	## quick-start / skip_menu behaviour is unchanged.
	var game_fields: Array = fields
	if game_fields.is_empty():
		game_fields = ScenarioCatalog.default_fields()
	var body := JSON.stringify({"fields": game_fields, "starting_credits": 10000})
	_enqueue("create", BASE_URL + "/games", HTTPClient.METHOD_POST, body, callback)


## Run Season (#537): one /step for RUN_SEASON_DAYS, and nothing else. The
## backend clamps it to the days left in the weather window, and rolls a
## finished window over exactly as Next Day does. callback receives the /step
## result, as Next Day's does.
func run_season(game_id: String, callback: Callable) -> void:
	step_day(game_id, RUN_SEASON_DAYS, callback)


func step_day(game_id: String, days: int, callback: Callable) -> void:
	var url := BASE_URL + "/games/" + game_id + "/step?days=" + str(days)
	_enqueue("step", url, HTTPClient.METHOD_POST, "", callback, days)


## The field-scoped calls name their field, with no default, so a caller can
## never act on, price or forecast a field it did not choose (#548).
func execute_action(
	game_id: String, field_id: String, action: String, params: Dictionary, callback: Callable
) -> void:
	var req := {"field_id": field_id, "action": action, "params": params}
	var url := BASE_URL + "/games/" + game_id + "/action"
	_enqueue("action", url, HTTPClient.METHOD_POST, JSON.stringify(req), callback)


func preview_action(
	game_id: String, field_id: String, action: String, params: Dictionary, callback: Callable
) -> void:
	## Fetch an action's estimated cost + affordability without executing it (#318).
	var req := {"field_id": field_id, "action": action, "params": params}
	var url := BASE_URL + "/games/" + game_id + "/action/preview"
	_enqueue("preview", url, HTTPClient.METHOD_POST, JSON.stringify(req), callback)


## The forecast, anchored on `field_id`'s first patch (#551).
func get_forecast(game_id: String, field_id: String, callback: Callable) -> void:
	var url := BASE_URL + "/games/" + game_id + "/forecast?field_id=" + field_id.uri_encode()
	_enqueue("forecast", url, HTTPClient.METHOD_GET, "", callback)


func get_report(game_id: String, callback: Callable) -> void:
	var url := BASE_URL + "/games/" + game_id + "/report"
	_enqueue("report", url, HTTPClient.METHOD_GET, "", callback)


## Game status plus each field's patch layout (#516). A 404 (the backend has
## lost the game, e.g. after a restart) reports {"not_found": true}, so the
## caller can tell it apart from an unreachable backend.
func get_game(game_id: String, callback: Callable) -> void:
	_enqueue("game", BASE_URL + "/games/" + game_id, HTTPClient.METHOD_GET, "", callback)


## `days` is a /step's day count, which sets its timeout; 0 for other calls.
func _enqueue(
	endpoint: String,
	url: String,
	method: HTTPClient.Method,
	body: String,
	callback: Callable,
	days: int = 0,
) -> void:
	var queue: Array = _queues[endpoint]
	queue.append({"url": url, "method": method, "body": body, "callback": callback, "days": days})
	_send_next(endpoint)


## Send the endpoint's oldest waiting call unless one is in flight, and give it
## the endpoint's timeout to be answered in (#556). A send request() rejects
## fails its own call only, and the queue moves on (#523).
func _send_next(endpoint: String) -> void:
	var queue: Array = _queues[endpoint]
	while not _in_flight.has(endpoint) and not queue.is_empty():
		var entry: Dictionary = queue.pop_front()
		if _send(endpoint, entry["url"], entry["method"], entry["body"]) == OK:
			_in_flight[endpoint] = entry
			_sends += 1
			entry["send"] = _sends
			var timer := get_tree().create_timer(_timeout_s(endpoint))
			timer.timeout.connect(_on_timed_out.bind(endpoint, _sends))
			return
		var callback: Callable = entry["callback"]
		callback.call(false, {})


## The client's network calls, _send and _cancel; tests override both to stub
## the transport.
func _send(endpoint: String, url: String, method: HTTPClient.Method, body: String) -> Error:
	var headers: PackedStringArray = []
	if method == HTTPClient.METHOD_POST:
		headers.append("Content-Type: application/json")
	var http: HTTPRequest = _requests[endpoint]
	return http.request(url, headers, method, body)


func _cancel(endpoint: String) -> void:
	var http: HTTPRequest = _requests[endpoint]
	http.cancel_request()


## How long `endpoint`'s call in flight may await a reply; tests override it to
## wait less. A /step gets 10 s + 0.5 s per day it asked for, up to its ceiling.
func _timeout_s(endpoint: String) -> float:
	if endpoint != "step":
		return TIMEOUT_S[endpoint]
	var days: int = _in_flight.get(endpoint, {}).get("days", RUN_SEASON_DAYS)
	return minf(STEP_TIMEOUT_BASE_S + STEP_TIMEOUT_PER_DAY_S * days, TIMEOUT_S["step"])


## Send number `send` on `endpoint` has gone unanswered for its whole timeout,
## unless it has been answered since, when this does nothing. HTTPRequest emits
## a reply from a deferred call, which SceneTree flushes before it runs timers,
## so a reply completed this frame has already landed; cancelling closes the
## connection, so none can land later (#556). The call then fails like any
## transport error: its caller hears back once, and the endpoint's queue moves on.
func _on_timed_out(endpoint: String, send: int) -> void:
	var entry: Dictionary = _in_flight.get(endpoint, {})
	if entry.get("send", 0) != send:
		return
	push_warning("[API] %s timed out; cancelled" % endpoint)
	_cancel(endpoint)
	_on_completed(HTTPRequest.RESULT_TIMEOUT, 0, PackedStringArray(), PackedByteArray(), endpoint)


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
