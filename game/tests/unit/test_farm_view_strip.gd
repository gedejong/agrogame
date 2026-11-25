extends GutTest
## The field strip in the farm view (#602, #472 C-d) on the two-field map: a
## card per field under UILayer, pressing one makes its field active as
## selecting a tile does, the highlight follows the active field, and the cards
## refresh after a step, a Plant and a Harvest.

const FarmViewScene = preload("res://scenes/farm_view.tscn")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")
const ActiveTest = preload("res://tests/unit/test_farm_view_active.gd")

var _auto_soil_view: bool


func before_each() -> void:
	_auto_soil_view = ProjectSettings.get_setting("agrogame/debug/auto_soil_view", false)
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", _auto_soil_view)
	GameState.game_id = ""


## The farm view on game "g", whose GET /games/{id} carries `fields`
## ({field_id: patches}), with a stub that answers previews and actions at once.
func _enter(fields: Dictionary) -> Node3D:
	GameState.game_id = "g"
	var api := ActiveTest.Stub.new()
	api.game_reply = [true, {"game_id": "g", "fields": fields}]
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	return view


## The Kenya maize and wheat scenario's two fields, one patch each (#658).
func _two_fields() -> Dictionary:
	var fields := {}
	for field: Dictionary in ScenarioCatalog.fields_for(ScenarioCatalog.option_count() - 1):
		fields[field["field_id"]] = field["patches"]
	return fields


func _pressed(view: Node3D) -> Array:
	return view._strip.cards().map(func(c: Button) -> bool: return c.button_pressed)


func _texts(view: Node3D) -> Array:
	return view._strip.cards().map(func(c: Button) -> String: return c.text)


func _sent_fields(view: Node3D) -> Array:
	var api: ActiveTest.Stub = view._api_client
	var sent: Array = api.calls.filter(func(c: Array) -> bool: return c[0] == "action")
	return sent.map(func(c: Array) -> String: return c[1])


func test_one_card_per_field_under_the_ui_layer() -> void:
	var view := _enter(_two_fields())
	assert_eq(view._strip.get_parent(), view.get_node("UILayer"))
	assert_eq(_texts(view).map(func(t: String) -> String: return t.get_slice(" ", 1)), ["1", "2"])
	assert_eq(_pressed(view), [true, false], "the first field starts active")
	var single := _enter({"field_1": ScenarioCatalog.default_patches()})
	assert_eq(single._strip.cards().size(), 1, "the default scenario shows one card")


func test_pressing_card_2_then_irrigate_sends_field_2() -> void:
	var view := _enter(_two_fields())
	view._strip.cards()[1].pressed.emit()
	assert_eq([view._active.id, view.active_field_label.text], ["field_2", "Field 2"])
	assert_eq(_pressed(view), [false, true], "card 2 is highlighted")
	view._on_irrigate()
	assert_eq(_sent_fields(view), ["field_2"])


func test_a_card_asks_for_the_forecast_and_previews_as_a_tile_does() -> void:
	var view := _enter(_two_fields())
	var api: ActiveTest.Stub = view._api_client
	view._strip.cards()[1].pressed.emit()
	assert_eq(api.forecasts.map(func(f: Array) -> String: return f[0]), ["field_2"])
	var previews: Array = api.calls.filter(func(c: Array) -> bool: return c[0] == "preview")
	assert_eq(previews.map(func(c: Array) -> String: return c[1]).count("field_2"), 4)


func test_selecting_a_tile_of_another_field_moves_the_highlight() -> void:
	var view := _enter(_two_fields())
	view._select_tile(0, 4)
	assert_eq(_pressed(view), [false, true])
	view._select_tile(5, 0)
	assert_eq(_pressed(view), [true, false])
	view._strip.cards()[0].button_pressed = false  # a click on the lit card releases it
	view._strip.cards()[0].pressed.emit()
	assert_eq(_pressed(view), [true, false], "reselecting keeps it lit")


func test_a_card_lets_go_of_a_tile_in_another_field_only() -> void:
	var view := _enter(_two_fields())
	view._select_tile(0, 0)
	view._strip.cards()[0].pressed.emit()
	assert_eq(view._selected_tile, Vector2i(0, 0), "a tile of the pressed field stays")
	view._strip.cards()[1].pressed.emit()
	assert_eq(view._selected_tile, Vector2i(-1, -1), "Plant cannot act on field_1 now")
	assert_eq(view._active.id, "field_2")


func test_the_cards_refresh_after_a_step_a_plant_and_a_harvest() -> void:
	var view := _enter(_two_fields())
	var dry := {"event_type": "WaterStressComputed", "data": {"stress": 0.32}}
	var maize := {"crop_key": "maize", "crop_stage": "vegetative", "events": []}
	var wheat := {"crop_key": "spring_wheat", "crop_stage": "vegetative", "events": [dry]}
	var step := {"day_number": 2, "date": "d", "weather": {}}
	step["patches"] = {"field_1": [maize], "field_2": [wheat]}
	view._on_step_complete(true, step)
	assert_eq(_texts(view)[0], "Field 1 · maize\nvegetative · OK")
	assert_eq(_texts(view)[1], "Field 2 · spring wheat\nvegetative · Water 32")
	var reply := {"cost_credits": 40, "balance_credits": 900}
	view._on_harvest_complete(true, reply, "spring_wheat", "field_2", 0)
	assert_eq(_texts(view)[1], "Field 2 · bare\nOK", "Harvest bares it")
	view._on_plant_complete(true, reply, "sorghum", "field_2", 0)
	assert_eq(_texts(view)[1], "Field 2 · sorghum\nplanted · OK", "Plant sows it")
	assert_eq(_texts(view)[0], "Field 1 · maize\nvegetative · OK", "field_1 is untouched")


func test_the_strip_clears_the_status_line_and_the_quick_status_card() -> void:
	var view := _enter(_two_fields())
	view._select_tile(0, 0)
	await wait_process_frames(2)
	var strip: Rect2 = view._strip.get_global_rect()
	assert_gt(strip.size.x, 0.0)
	assert_true(strip.position.y >= view.status_label.get_global_rect().end.y, "below it")
	assert_false(strip.intersects(view._quick_status.get_global_rect()), "beside the card")
	var centre: float = view.get_viewport().get_visible_rect().size.x / 2.0
	assert_almost_eq(strip.get_center().x, centre, 1.0, "centred")
