extends GutTest
## The active field in the farm view (#601, #472 C-c) on the two-field map:
## selecting a tile picks the field Irrigate, Fertilize, Tillage and Lime act
## on, the previews and forecast follow it, and each status line names it.

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")

var _auto_cutaway: bool


## Records previews and actions, and answers each at once.
class Stub:
	extends FarmViewTest.ApiStub

	func preview_action(
		_id: String, field_id: String, action: String, params: Dictionary, cb: Callable
	) -> void:
		calls.append(["preview", field_id, action, params])
		cb.call(true, {"cost_credits": 5, "balance_credits": 900})

	func execute_action(
		_id: String, field_id: String, action: String, params: Dictionary, cb: Callable
	) -> void:
		calls.append(["action", field_id, action, params])
		cb.call(true, {"action": action, "cost_credits": 5, "balance_credits": 900})


func before_each() -> void:
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)
	GameState.game_id = ""


## The Kenya maize and wheat scenario's two fields, one patch each.
func _enter() -> Node3D:
	GameState.game_id = "g"
	var api := Stub.new()
	var fields := {}
	for field: Dictionary in ScenarioCatalog.fields_for(ScenarioCatalog.option_count() - 1):
		fields[field["field_id"]] = field["patches"]
	api.game_reply = [true, {"game_id": "g", "fields": fields}]
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	return view


func _escape(view: Node3D) -> void:
	var key := InputEventKey.new()
	key.pressed = true
	key.keycode = KEY_ESCAPE
	view._unhandled_input(key)


## The (field, action, params) of every action sent, in order.
func _actions(api: Stub) -> Array:
	var sent: Array = api.calls.filter(func(c: Array) -> bool: return c[0] == "action")
	return sent.map(func(c: Array) -> Array: return c.slice(1))


func test_starts_on_the_first_field_and_follows_selection_through_escape() -> void:
	var view := _enter()
	assert_eq(view._active.id, "field_1")
	assert_eq(view.active_field_label.text, "Field 1")
	view._select_tile(0, 4)
	assert_eq([view._active.id, view.active_field_label.text], ["field_2", "Field 2"])
	_escape(view)
	assert_eq(view._selected_tile, Vector2i(-1, -1), "deselected")
	assert_eq(view._active.id, "field_2", "Esc keeps the active field")
	view._select_tile(0, 0)
	assert_eq(view.active_field_label.text, "Field 1", "the label follows a change")


func test_the_label_sits_in_the_action_bar_before_irrigate() -> void:
	var view := _enter()
	var bar: Node = view.irrigate_btn.get_parent()
	assert_eq(view.active_field_label.get_parent(), bar)
	assert_eq(view.active_field_label.get_index() + 1, view.irrigate_btn.get_index())


func test_each_field_action_names_the_active_field() -> void:
	var view := _enter()
	var api: Stub = view._api_client
	view._select_tile(0, 4)
	view._on_irrigate()
	_escape(view)
	view._on_tillage()
	view._select_tile(0, 0)
	view._on_lime_selected(2000.0, 10)
	view._on_fertilizer_selected(0)
	var fields: Array = _actions(api).map(func(a: Array) -> String: return a[0])
	assert_eq(fields, ["field_2", "field_2", "field_1", "field_1"])
	var kinds: Array = _actions(api).map(func(a: Array) -> String: return a[1])
	assert_eq(kinds, ["irrigate", "tillage", "lime", "fertilize"])


func test_status_lines_name_the_field_acted_on() -> void:
	var view := _enter()
	view._select_tile(0, 4)
	var presses: Array = [
		["irrigate", view._on_irrigate],
		["fertilize", view._on_fertilizer_selected.bind(0)],
		["tillage", view._on_tillage],
		["lime", view._on_lime_selected.bind(2000.0, 10)],
	]
	for press: Array in presses:
		(press[1] as Callable).call()
		assert_string_contains(view.status_label.text, "Field 2", press[0])
		assert_string_contains(view.status_label.text, press[0], "the action too")
	view._on_crop_selected(FarmView.AVAILABLE_CROPS.find("sorghum"))
	assert_string_contains(view.status_label.text, "Planted sorghum on Field 2")
	view._on_harvest_complete(true, {"profit_credits": 40}, "sorghum", "field_2", 0)
	assert_string_contains(view.status_label.text, "Field 2")
	assert_string_contains(view.status_label.text, "farm profit 40")


func test_after_a_step_all_four_previews_and_the_forecast_carry_the_active_field() -> void:
	var view := _enter()
	var api: Stub = view._api_client
	view._select_tile(0, 4)
	api.calls.clear()
	view._on_step_complete(true, {"day_number": 2, "date": "d", "weather": {}, "patches": {}})
	var previews: Array = api.calls.filter(func(c: Array) -> bool: return c[0] == "preview")
	assert_eq(previews.map(func(c: Array) -> String: return c[1]), _four("field_2"))
	assert_eq(
		previews.map(func(c: Array) -> String: return c[2]),
		["irrigate", "fertilize", "tillage", "lime"]
	)
	assert_eq(api.forecasts[-1][0], "field_2", "the forecast is for it too")


func _four(field: String) -> Array:
	return [field, field, field, field]


func test_a_change_asks_for_the_forecast_and_previews_but_a_reselect_does_not() -> void:
	var view := _enter()
	var api: Stub = view._api_client
	view._select_tile(0, 4)
	assert_eq(api.forecasts.size(), 1, "the change asks for field_2's forecast")
	assert_eq(api.forecasts[0][0], "field_2")
	var previews: Array = api.calls.filter(func(c: Array) -> bool: return c[0] == "preview")
	assert_eq(previews.map(func(c: Array) -> String: return c[1]), _four("field_2"))
	api.calls.clear()
	view._select_tile(1, 5)  # field_2 again
	_escape(view)
	view._select_tile(0, 4)
	assert_eq(api.calls, [], "reselecting the active field asks for nothing")


func test_quick_changes_leave_one_forecast_in_flight_and_end_on_the_last_field() -> void:
	var view := _enter()
	var api: Stub = view._api_client
	view._select_tile(0, 4)
	view._select_tile(0, 0)
	view._select_tile(0, 4)
	assert_eq(api.forecasts.size(), 1, "one request in flight")
	var first: Array = api.forecasts.pop_front()
	first[1].call(true, {"forecast": []})
	assert_eq(api.forecasts.size(), 1, "re-asked once")
	assert_eq(api.forecasts[0][0], "field_2", "for the last active field")
