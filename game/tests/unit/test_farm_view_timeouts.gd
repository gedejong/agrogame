extends GutTest
## The farm view against a backend that never answers (#556): each request times
## out, the action bar comes back with the failure shown, and a reply that turns
## up after its timeout is not applied. Kept apart from test_farm_view.gd, which
## is at gdlint's public-method cap. The view runs over test_api_client.gd's
## StubClient: the real client and its queues, every transport stubbed (#534).

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")

var _auto_cutaway: bool


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)
	GameState.game_id = ""


## A farm view on game "g" over StubClient, with tile (0, 0), patch 0, selected
## and carrying a standing crop.
func _stub_view() -> Node3D:
	GameState.game_id = ""  # no hand-over, so _ready fetches nothing
	var api: ApiClientTest.StubClient = ApiClientTest.StubClient.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._game_id = "g"
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 2
	view._select_tile(0, 0)
	return view


## Whether every action-bar button is `disabled`.
func _bar_is(view: Node3D, disabled: bool) -> bool:
	for btn: String in FarmViewTest._BAR:
		var button: Button = view.get(btn)
		if button.disabled != disabled:
			return false
	return true


## What a reply landing in the view could change: tiles, last step, the labels
## and further sends.
func _view_snapshot(view: Node3D, api: ApiClientTest.StubClient) -> Array:
	return [
		view._tile_data.duplicate(true),
		view._last_step_data.duplicate(true),
		view.date_label.text,
		view.credits_label.text,
		view.status_label.text,
		api.sends.size(),
	]


func test_a_hung_step_or_action_times_out_and_lifts_the_bar() -> void:
	# #556 AC2/AC3: a /step or /action never answered held the bar for good,
	# since #534 holds it until the reply is applied. Its timeout lifts the bar
	# with the press's failure text, its reply turning up later is not applied,
	# and the next press goes through as usual.
	var presses: Array = [
		["_on_next_day", "step", "Step failed — backend error"],
		["_on_ff_all", "step", "Season failed — backend error"],
		["_on_irrigate", "action", "Action failed"],
		["_on_crop_selected", "action", "Plant failed"],
		["_on_harvest_pressed", "action", "Harvest failed"],
	]
	var replies: Dictionary = FarmViewTest._REPLY
	for press: Array in presses:
		var view := _stub_view()
		var api: ApiClientTest.StubClient = view._api_client
		var endpoint: String = press[1]
		api.timeouts_for[endpoint] = [0.05]
		var method: String = press[0]
		if method == "_on_crop_selected":
			view.call(method, 0)
		else:
			view.call(method)
		assert_true(api.awaiting(endpoint), "%s: sent, and never answered" % method)
		assert_true(_bar_is(view, true), "%s: the bar is held" % method)
		var lifted := func() -> bool: return _bar_is(view, false)
		assert_true(await wait_until(lifted, 1.0), "%s: its timeout lifted the bar" % method)
		assert_eq(view.status_label.text, press[2], method)
		assert_eq(api.cancels, [endpoint], "%s: the hung request was cancelled" % method)
		assert_push_warning("%s timed out" % endpoint)
		var before := _view_snapshot(view, api)
		api.reply_ok(endpoint, replies[endpoint])
		assert_push_error("no %s in flight" % endpoint)
		assert_eq(_view_snapshot(view, api), before, "%s: its late reply changed nothing" % method)
		# A second round on the same view: the client recovers.
		view._on_next_day()
		api.reply_ok("step", replies["step"])
		assert_eq(
			view.date_label.text, "Day 2 | 2026-05-02", "%s: the next Next Day applies" % method
		)
		assert_true(_bar_is(view, false), "%s: and lifts the bar" % method)


## Answer the refresh's previews from _PREVIEW_ACTIONS[first] on, the i-th
## priced at `base + i`, and check each button then shows its own price.
func _answer_chain(view: Node3D, api: ApiClientTest.StubClient, first: int, base: int) -> void:
	var specs: Array[Dictionary] = FarmView._PREVIEW_ACTIONS
	for i in range(first, specs.size()):
		assert_true(api.awaiting("preview"), "%s sent" % specs[i]["action"])
		var reply := {"cost_credits": base + i, "balance_credits": 900, "affordable": true}
		api.reply_ok("preview", reply)
	assert_false(api.awaiting("preview"), "the chain ran to its end")
	for i in range(first, specs.size()):
		var spec: Dictionary = specs[i]
		var variable: bool = spec.get("variable_cost", false)
		var label := ActionCost.format_button_label(spec["label"], base + i, variable)
		assert_eq(view._action_button_for(spec["action"]).text, label, "%s priced" % spec["label"])


func test_a_timed_out_preview_does_not_stall_the_cost_refresh() -> void:
	# #556 AC4: #523's preview chain moves past a preview never answered, which
	# prices nothing; the ones after it are sent and priced. The next refresh
	# then prices every button.
	var view := _stub_view()
	var api: ApiClientTest.StubClient = view._api_client
	api.timeouts_for["preview"] = [0.05]
	var unpriced: String = view.irrigate_btn.text
	view._refresh_action_costs()
	assert_true(await wait_until(func() -> bool: return api.cancels == ["preview"], 1.0))
	assert_push_warning("preview timed out")
	_answer_chain(view, api, 1, 10)  # Irrigate's preview, the first, timed out
	assert_eq(view.irrigate_btn.text, unpriced, "the timed-out preview priced nothing")
	view._refresh_action_costs()
	_answer_chain(view, api, 0, 20)
	var previews: Array = api.sends.filter(func(s: Array) -> bool: return s[0] == "preview")
	var sent: Array = previews.map(
		func(s: Array) -> String: return JSON.parse_string(s[3])["action"]
	)
	var chain := ["irrigate", "fertilize", "tillage", "lime"]
	assert_eq(sent, chain + chain, "each refresh previewed every action once, in order")
