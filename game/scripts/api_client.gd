extends Node
## HTTP client for communicating with the FastAPI backend.
## Configured for local development at localhost:8000.

const BASE_URL := "http://localhost:8000/api/v1"

var _http_request: HTTPRequest
var _callback: Callable


func _ready() -> void:
	_http_request = HTTPRequest.new()
	add_child(_http_request)
	_http_request.request_completed.connect(_on_request_completed)


func create_game(callback: Callable) -> void:
	"""POST /api/v1/games with default field config."""
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
							"soil_profile_key": "loam_temperate",
							"crop_key": "maize",
							"climate_key": "netherlands_temperate",
							"area_fraction": 1.0
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
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200:
		_callback.call(false, {})
		return
	var json := JSON.new()
	var parse_result := json.parse(body.get_string_from_utf8())
	if parse_result != OK:
		_callback.call(false, {})
		return
	_callback.call(true, json.data)
