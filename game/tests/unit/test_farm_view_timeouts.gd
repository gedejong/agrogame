extends GutTest
## The farm view against a backend that never answers (#556): each request times
## out, the action bar comes back with the failure shown, and a reply that turns
## up after its timeout is not applied. A failed action re-reads the game, which
## the server may have changed anyway, and a failed layout load retries (#564).
## Kept apart from test_farm_view.gd, which is at gdlint's public-method cap. The
## view runs over test_api_client.gd's StubClient: the real client and its
## queues, every transport stubbed (#534).

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")
const FarmViewTest = preload("res://tests/unit/test_farm_view.gd")

var _auto_cutaway: bool


## StubClient over a server that applies each /action as the backend does and
## never replies to it (#564), as #559's validation saw live. GET /games/{id} is
## answered from that server's state by game(). field_2's lone patch is rice, so
## a match by patch index alone would put rice on field_1's patch 0.
class ApplyingStub:
	extends ApiClientTest.StubClient
	var balance: int = 1000
	var fields: Dictionary = {
		"field_1": [{"crop_key": "maize"}, {"crop_key": "maize"}, {"crop_key": "maize"}],
		"field_2": [{"crop_key": "rice"}],
	}

	func _send(endpoint: String, url: String, method: HTTPClient.Method, body: String) -> Error:
		if endpoint == "action":
			var req: Dictionary = JSON.parse_string(body)
			var params: Dictionary = req["params"]
			var patch: Dictionary = fields[req["field_id"]][int(params.get("patch_idx", 0))]
			match req["action"]:
				"harvest":
					patch["crop_key"] = ""
					balance += 300
				"plant":
					patch["crop_key"] = params["crop_key"]
					balance -= 67
				_:
					balance -= 40
		return super(endpoint, url, method, body)

	func game() -> Dictionary:
		return {"game_id": "g", "balance_credits": balance, "fields": fields.duplicate(true)}


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)
	GameState.game_id = ""


## A farm view on game "g" over StubClient, or `api` when given, with tile
## (0, 0), patch 0, selected and carrying a standing crop.
func _stub_view(api: ApiClientTest.StubClient = null) -> Node3D:
	GameState.game_id = ""  # no hand-over, so _ready fetches nothing
	if api == null:
		api = ApiClientTest.StubClient.new()
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


## Each column's value of `key` on row 0, checked identical on row 5.
func _band(view: Node3D, key: String) -> Array:
	var out: Array = []
	for col in range(6):
		assert_eq(view._tile_data[30 + col][key], view._tile_data[col][key], "column-wide")
		out.append(view._tile_data[col][key])
	return out


## Answer the cost refresh's previews, each at the stub server's balance.
func _answer_previews(api: ApplyingStub) -> void:
	for i in range(FarmView._PREVIEW_ACTIONS.size()):
		assert_true(api.awaiting("preview"), "the costs are refreshed")
		api.reply_ok("preview", {"cost_credits": 5, "balance_credits": api.balance})


func test_an_action_the_server_applied_without_replying_is_reconciled() -> void:
	# #564 AC1: a timed-out /action can still apply on the server. Once the bar
	# is back, the view re-reads the game and takes its balance and every
	# field's crops as the truth. Three rounds on one view, on patch 1's band:
	# Harvest clears its crop, Plant sows sorghum, Irrigate only charges.
	var api := ApplyingStub.new()
	var view := _stub_view(api)
	var growing := {"crop_key": "maize", "crop_stage": "vegetative", "lai": 2.0}
	view._apply_patch_data({"field_1": [growing, growing, growing]})
	view._select_tile(2, 0)
	var sorghum: int = FarmView.AVAILABLE_CROPS.find("sorghum")
	var rounds: Array = [
		[view._on_harvest_pressed, "Harvest failed", "", 1300],
		[view._on_crop_selected.bind(sorghum), "Plant failed", "sorghum", 1233],
		[view._on_irrigate, "Action failed", "sorghum", 1193],
	]
	for r: Array in rounds:
		var failure: String = r[1]
		api.timeouts_for["action"] = [0.05]
		var press: Callable = r[0]
		press.call()
		var lifted := func() -> bool: return not view.next_day_btn.disabled
		assert_true(await wait_until(lifted, 1.0), "%s: the bar is back" % failure)
		assert_push_warning("action timed out")
		assert_eq(view.status_label.text, failure, "the failure shows while the game is re-read")
		assert_true(api.awaiting("game"), "%s: the game is re-read" % failure)
		api.reply_ok("game", api.game())
		var crop: String = r[2]
		assert_eq(view.credits_label.text, str(r[3]), "%s: the server's balance" % failure)
		assert_eq(view._balance_credits, r[3], "%s: and the pickers' balance" % failure)
		var crops := ["maize", "maize", crop, crop, "maize", "maize"]
		assert_eq(_band(view, "crop_key"), crops, "%s: field_1's crops, no rice" % failure)
		assert_eq(_band(view, "lai"), [2.0, 2.0, 0.0, 0.0, 2.0, 2.0], "the others keep growing")
		await wait_process_frames(1)  # the replaced plants are queue_free'd
		var drawn: bool = view._crop_sprites[2][0].get_child_count() > 0
		assert_eq(drawn, not crop.is_empty(), "%s: patch 1's tiles are redrawn" % failure)
		var reread := "%s; credits and crops re-read from the server" % failure
		assert_eq(view.status_label.text, reread)
		assert_eq(view.harvest_btn.disabled, crop.is_empty(), "%s: Harvest follows" % failure)
		assert_false(view.next_day_btn.disabled, "%s: the bar stays released" % failure)
		_answer_previews(api)
	var actions: Array = api.sends.filter(func(s: Array) -> bool: return s[0] == "action")
	assert_eq(actions.size(), 3, "each action sent once, none repeated")


func test_a_re_read_landing_after_a_newer_reply_changes_nothing() -> void:
	# #564: the bar is back while the game is re-read (#534 AC8), so a Next Day
	# can go out meanwhile. Its reply is the newer state, so a re-read landing
	# after it is dropped; a re-read that fails changes nothing either.
	var api := ApplyingStub.new()
	var view := _stub_view(api)
	view._on_irrigate()
	api.reply("action", HTTPRequest.RESULT_CONNECTION_ERROR, 0, "")  # applied, then dropped
	assert_eq(view.status_label.text, "Action failed")
	view._on_next_day()
	var step: Dictionary = FarmViewTest._REPLY["step"].duplicate()
	step["balance_credits"] = 777
	api.reply_ok("step", step)
	assert_eq(view.credits_label.text, "777", "the step's balance")
	var before := _view_snapshot(view, api)
	assert_true(api.awaiting("game"), "the re-read is still in flight")
	api.reply_ok("game", api.game())
	assert_eq(_view_snapshot(view, api), before, "the older re-read is dropped")
	view._on_tillage()
	api.reply("action", HTTPRequest.RESULT_SUCCESS, 400, "{}")
	before = _view_snapshot(view, api)
	api.reply("game", HTTPRequest.RESULT_CANT_CONNECT, 0, "")
	assert_eq(_view_snapshot(view, api), before, "a failed re-read changes nothing")


func test_a_failed_layout_load_retries_with_backoff_until_it_loads() -> void:
	# #564 AC3: a failed or timed-out GET /games/{id} left the farm view stuck.
	# It now retries on its own after 1 s, doubling to 30 s, with the bar held
	# (#516) until the layout loads; a 404 still returns to the title.
	GameState.game_id = "g"
	var api: ApiClientTest.StubClient = ApiClientTest.StubClient.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._load_retry_s = 0.05
	# A transport error, a 500 and a hung request, each followed by a retry.
	api.reply("game", HTTPRequest.RESULT_CANT_CONNECT, 0, "")
	assert_true(await wait_until(func() -> bool: return api.sends.size() == 2, 1.0), "retried")
	api.timeouts_for["game"] = [0.05]  # the send after the next one hangs
	api.reply("game", HTTPRequest.RESULT_SUCCESS, 500, "{}")
	assert_true(await wait_until(func() -> bool: return api.sends.size() == 3, 1.0), "again")
	var hung := func() -> bool: return view._load_failures == 3
	assert_true(await wait_until(hung, 1.0), "the third load timed out")
	assert_push_warning("game timed out")
	assert_string_contains(view.status_label.text, "could not load game g, retrying in")
	assert_true(_bar_is(view, true), "the bar stays held while the layout is missing")
	assert_true(await wait_until(func() -> bool: return api.sends.size() == 4, 1.0), "and again")
	var sandy := {"soil_profile_key": "sandy_subsaharan", "crop_key": "maize"}
	api.reply_ok("game", {"game_id": "g", "fields": {"field_1": [sandy]}})
	assert_false(view.next_day_btn.disabled, "the bar is released once the layout loads")
	assert_eq(view._tile_data[35]["soil_type"], "sandy", "the loaded layout")
	assert_eq(view._load_failures, 0, "the backoff starts over")
	var endpoints: Array = api.sends.map(func(s: Array) -> String: return s[0])
	assert_eq(endpoints, ["game", "game", "game", "game"], "nothing else sent")
	# The delays double from _load_retry_s and stop at LOAD_RETRY_MAX_S.
	view._load_retry_s = 1.0
	var shown: Array = []
	for i in range(7):
		view._on_game_loaded(false, {})
		shown.append(view.status_label.text.get_slice("retrying in ", 1))
	assert_eq(shown, ["1 s", "2 s", "4 s", "8 s", "16 s", "30 s", "30 s"])
