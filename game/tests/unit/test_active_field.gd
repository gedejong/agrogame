extends GutTest
## ActiveField (#601): the field actions, previews and the forecast name, its
## action-bar label, and the forecast request that keeps one in flight.


## Holds each forecast request until the test answers it.
class Api:
	extends Node
	var asked: Array = []  # field ids, in request order
	var _callbacks: Array = []

	func get_forecast(_game_id: String, field_id: String, callback: Callable) -> void:
		asked.append(field_id)
		_callbacks.append(callback)

	func reply(forecast: Array = []) -> void:
		var cb: Callable = _callbacks.pop_front()
		cb.call(true, {"forecast": forecast})


var _shown: Array = []


func _make() -> Array:
	var label := Label.new()
	add_child_autofree(label)
	var api := Api.new()
	add_child_autofree(api)
	_shown = []
	var active := ActiveField.new(
		label, api, func(ok: bool, data: Dictionary) -> void: _shown.append([ok, data])
	)
	active.reset([{"field_id": "field_1", "patches": []}, {"field_id": "field_2", "patches": []}])
	return [active, label, api]


func test_display_name_capitalises_the_field_id() -> void:
	assert_eq(ActiveField.display_name("field_2"), "Field 2")


func test_starts_on_the_first_field_and_labels_it() -> void:
	var made := _make()
	assert_eq((made[0] as ActiveField).id, "field_1")
	assert_eq((made[1] as Label).text, "Field 1")
	(made[0] as ActiveField).reset([])
	assert_eq((made[0] as ActiveField).id, "", "no field leaves it unset")


func test_select_reports_a_change_only() -> void:
	var made := _make()
	var active: ActiveField = made[0]
	assert_true(active.select("field_2"))
	assert_eq([active.id, (made[1] as Label).text], ["field_2", "Field 2"])
	assert_false(active.select("field_2"), "reselecting is no change")


func test_two_changes_in_one_round_trip_leave_one_request_and_the_last_field() -> void:
	var made := _make()
	var active: ActiveField = made[0]
	var api: Api = made[2]
	active.request_forecast("g")
	active.select("field_2")
	active.request_forecast("g")
	active.select("field_1")
	active.request_forecast("g")
	active.select("field_2")
	active.request_forecast("g")
	assert_eq(api.asked, ["field_1"], "one in flight")
	api.reply([1])
	assert_eq(_shown, [], "the first field's forecast is stale, so it is not shown")
	assert_eq(api.asked, ["field_1", "field_2"], "one more, for the last active field")
	api.reply([2])
	assert_eq(_shown, [[true, {"forecast": [2]}]], "the panel ends on field_2's forecast")
	assert_eq(api.asked.size(), 2, "and nothing more is asked")


func test_a_step_during_a_request_asks_again_for_the_same_field() -> void:
	var made := _make()
	var active: ActiveField = made[0]
	var api: Api = made[2]
	active.request_forecast("g")
	active.request_forecast("g")
	api.reply([1])
	assert_eq(api.asked, ["field_1", "field_1"], "the newer day's forecast is asked")
	api.reply([2])
	assert_eq(_shown.size(), 1, "only the newest reply is shown")
