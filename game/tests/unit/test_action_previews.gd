extends GutTest
## ActionPreviews (#601): one refresh previews every priced action on the named
## field, in order, and each reply lands on its own action's button. The
## overlap and timeout cases are exercised through the farm view
## (test_farm_view.gd, test_farm_view_timeouts.gd).


## Records each preview and answers it from `replies` at once.
class Api:
	extends Node
	var calls: Array = []
	var affordable: bool = true

	func preview_action(
		_id: String, field_id: String, action: String, params: Dictionary, cb: Callable
	) -> void:
		calls.append([field_id, action, params])
		cb.call(true, {"cost_credits": 7, "balance_credits": 500, "affordable": affordable})


func _buttons() -> Dictionary:
	var out := {}
	for spec: Dictionary in ActionPreviews.ACTIONS:
		var btn := Button.new()
		add_child_autofree(btn)
		out[spec["action"]] = btn
	return out


func test_refresh_previews_every_action_on_the_field_in_order() -> void:
	var api := Api.new()
	add_child_autofree(api)
	var balances: Array = []
	var held := [false]
	var previews := ActionPreviews.new(
		api,
		_buttons(),
		func(b: int) -> void: balances.append(b),
		func() -> bool: return held[0],
	)
	previews.refresh("g", "field_2")
	var sent: Array = api.calls.map(func(c: Array) -> String: return c[0] + "/" + c[1])
	assert_eq(sent, ["field_2/irrigate", "field_2/fertilize", "field_2/tillage", "field_2/lime"])
	assert_eq(api.calls[0][2], {"amount_mm": 20}, "the fixed params the handler sends")
	assert_eq(balances, [500, 500, 500, 500])
	assert_eq(previews.button_for("irrigate").text, "Irrigate (7cr)")
	assert_eq(previews.button_for("lime").text, "Lime (from 7cr)")
	assert_null(previews.button_for("plant"), "no cost on an unpriced action")


func test_a_held_bar_or_an_unaffordable_cost_disables_the_button() -> void:
	var api := Api.new()
	add_child_autofree(api)
	var held := [true]
	var previews := ActionPreviews.new(
		api, _buttons(), func(_b: int) -> void: pass, func() -> bool: return held[0]
	)
	previews.refresh("g", "field_1")
	assert_true(previews.button_for("tillage").disabled, "the bar holds it")
	held[0] = false
	previews.refresh("g", "field_1")
	assert_false(previews.button_for("tillage").disabled)
	api.affordable = false
	previews.refresh("g", "field_1")
	assert_true(previews.button_for("tillage").disabled, "unaffordable")
