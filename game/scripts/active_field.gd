class_name ActiveField
extends RefCounted
## The field Irrigate, Fertilize, Tillage and Lime act on, the four cost previews
## price and the forecast describes (#601, #472 G2 (a)). It starts as the
## layout's first field and follows the player's tile selection; Esc keeps it.
## Its label in the action bar names it. It also owns the forecast request, so
## that a quick run of field changes leaves one request in flight and the panel
## on the last active field's forecast (the single-callback defect class of #534).

var id: String = ""
var _label: Label
var _api: Node
var _game_id: String = ""
var _apply: Callable  # (success: bool, data: Dictionary) -> void, the forecast's consumer
var _in_flight: bool = false
var _stale: bool = false  # the field changed, or a step landed, since the request left


func _init(label: Label, api: Node, apply_forecast: Callable) -> void:
	_label = label
	_api = api
	_apply = apply_forecast
	UiTheme.style_label(label, "value")


## "Field 2" for "field_2".
static func display_name(field_id: String) -> String:
	return field_id.capitalize()


## Start on the first of `fields` ([{field_id, patches}]); no field leaves it unset.
func reset(fields: Array) -> void:
	_make_active("" if fields.is_empty() else fields[0]["field_id"])


## Make `field_id` active. True when that changed it (not on reselecting it).
func select(field_id: String) -> bool:
	if field_id == id:
		return false
	_make_active(field_id)
	return true


func _make_active(field_id: String) -> void:
	id = field_id
	_label.text = display_name(id)


## Ask for the active field's forecast. While one request is out, this only
## notes that it is stale and the reply re-asks, so at most one is in flight.
func request_forecast(game_id: String) -> void:
	_game_id = game_id
	if _in_flight:
		_stale = true
		return
	_send()


func _send() -> void:
	_in_flight = true
	_stale = false
	var asked := id
	_api.get_forecast(
		_game_id, asked, func(ok: bool, data: Dictionary) -> void: _on_reply(ok, data, asked)
	)


func _on_reply(success: bool, data: Dictionary, asked: String) -> void:
	_in_flight = false
	if _stale or asked != id:
		_send()  # never show a forecast for a field no longer active
		return
	_apply.call(success, data)
