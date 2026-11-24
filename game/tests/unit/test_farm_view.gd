extends GutTest

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")
## The nine action-bar buttons a /step or /action in flight holds (#534 AC5).
const _BAR: Array[String] = [
	"next_day_btn",
	"ff7_btn",
	"ff_all_btn",
	"irrigate_btn",
	"fertilize_btn",
	"tillage_btn",
	"lime_btn",
	"plant_btn",
	"harvest_btn",
]
## The bar buttons whose press sends at once rather than opening a picker.
const _SENDING: Array[String] = [
	"next_day_btn", "ff7_btn", "ff_all_btn", "irrigate_btn", "tillage_btn", "harvest_btn"
]
## A 200 reply per mutating endpoint, enough for every farm-view handler.
const _REPLY := {
	"step": {"day_number": 2, "date": "2026-05-02", "weather": {}, "patches": {}},
	"action": {"action": "irrigate", "cost_credits": 5, "balance_credits": 900},
}

var _auto_cutaway: bool


## Stands in for ApiClient: records calls and answers at once (or on demand,
## with defer_game), so no test touches the network.
class ApiStub:
	extends Node
	var calls: Array = []
	var game_reply: Array = [true, {}]
	var defer_game: bool = false
	var _game_cb: Callable
	## The forecasts asked for, as [field_id, callback], answered by the test.
	var forecasts: Array = []

	func get_game(game_id: String, callback: Callable) -> void:
		calls.append(["get_game", game_id])
		_game_cb = callback
		if not defer_game:
			reply_game(game_reply[0], game_reply[1])

	func reply_game(ok: bool, data: Dictionary) -> void:
		_game_cb.call(ok, data)

	func get_forecast(_game_id: String, field_id: String, callback: Callable) -> void:
		calls.append(["forecast", field_id])
		forecasts.append([field_id, callback])

	func create_game(callback: Callable, _fields: Array = []) -> void:
		calls.append(["create_game"])
		callback.call(true, {"game_id": "created"})

	func step_day(game_id: String, days: int, _callback: Callable) -> void:
		calls.append(["step_day", game_id, days])

	func execute_action(
		_id: String, field_id: String, action: String, params: Dictionary, _cb: Callable
	) -> void:
		calls.append(["action", field_id, action, params])


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)
	GameState.game_id = ""


## Enter the farm view as the title screen does, with `handed_over` as the id.
func _enter(handed_over: String, reply: Array = [true, {}], defer: bool = false) -> Node3D:
	GameState.game_id = handed_over
	var api := ApiStub.new()
	api.game_reply = reply
	api.defer_game = defer
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	return view


func _game(patches: Array) -> Array:
	return [true, {"game_id": "g", "fields": {"field_1": patches}}]


func _patch(soil: String) -> Dictionary:
	return {"soil_profile_key": soil, "crop_key": "maize", "climate_key": "c", "area_fraction": 0.5}


## One value per column, read from row 0 and checked identical on row 5.
func _band(view: Node3D, key: String) -> Array:
	var out: Array = []
	for col in range(6):
		assert_eq(view._tile_data[30 + col][key], view._tile_data[col][key], "column-wide")
		out.append(view._tile_data[col][key])
	return out


func test_script_loads() -> void:
	assert_not_null(FarmView, "FarmView script loads")


func test_scene_file_exists() -> void:
	assert_true(
		FileAccess.file_exists("res://scenes/farm_view.tscn"),
		"3D scene file exists",
	)


func test_grid_dimensions() -> void:
	assert_eq(FarmView.GRID_COLS, 6, "6 columns")
	assert_eq(FarmView.GRID_ROWS, 6, "6 rows")


func test_available_crops() -> void:
	assert_true(FarmView.AVAILABLE_CROPS.size() >= 3)
	assert_has(FarmView.AVAILABLE_CROPS, "maize")
	assert_has(FarmView.AVAILABLE_CROPS, "spring_wheat")


func test_preview_actions_cover_fixed_cost_buttons() -> void:
	# Cost-preview specs (#318) must carry an action, label and params each,
	# so the previewed cost label matches the executed action's deduction.
	var actions: Array = []
	for spec: Dictionary in ActionPreviews.ACTIONS:
		assert_true(spec.has("action"), "spec has action")
		assert_true(spec.has("label"), "spec has label")
		assert_true(spec.has("params"), "spec has params")
		actions.append(spec["action"])
	assert_has(actions, "irrigate")
	assert_has(actions, "fertilize")
	assert_has(actions, "tillage")
	assert_has(actions, "lime")


func test_preview_irrigate_params_match_handler() -> void:
	# The irrigate handler sends amount_mm=20; the preview spec must agree
	# so the shown cost equals the ledger deduction.
	for spec: Dictionary in ActionPreviews.ACTIONS:
		if spec["action"] == "irrigate":
			assert_eq(spec["params"].get("amount_mm"), 20)


func test_preview_fertilize_is_variable_cost() -> void:
	# Fertilize spans several priced tiers (#349 review), so its spec carries no
	# fixed params: the preview resolves the cheapest tier at request time and
	# the button shows a "from" price, gating only when no tier is affordable.
	for spec: Dictionary in ActionPreviews.ACTIONS:
		if spec["action"] == "fertilize":
			assert_true(spec.get("variable_cost", false), "fertilize previews a from-price")
			assert_true(spec["params"].is_empty(), "fertilize params resolved dynamically")


func test_preview_lime_is_variable_cost() -> void:
	# Lime is offered in t/ha tiers through its own picker (#465), so like
	# fertilize it previews the cheapest tier as a "from" price rather than a
	# fixed cost.
	for spec: Dictionary in ActionPreviews.ACTIONS:
		if spec["action"] == "lime":
			assert_true(spec.get("variable_cost", false), "lime previews a from-price")
			assert_true(spec["params"].is_empty(), "lime params resolved dynamically")


func test_ready_keeps_handed_over_game() -> void:
	var view := _enter("handed-over", _game([_patch("sandy_subsaharan")]))
	assert_eq(view._game_id, "handed-over", "id survives _ready")
	assert_eq(GameState.game_id, "handed-over", "GameState is not cleared")
	view._on_next_day()
	var api: ApiStub = view._api_client
	assert_eq(api.calls, [["get_game", "handed-over"], ["step_day", "handed-over", 1]])


func test_ensure_game_creates_only_without_handover() -> void:
	var view := _enter("")
	var api: ApiStub = view._api_client
	assert_eq(api.calls, [], "nothing to fetch without a hand-over")
	view._on_next_day()
	assert_eq(api.calls, [["create_game"], ["step_day", "created", 1]])


func test_one_patch_scenario_fills_all_columns() -> void:
	var view := _enter("g", _game([_patch("sandy_subsaharan")]))
	for tile: Dictionary in view._tile_data:
		assert_eq([tile["patch_idx"], tile["soil_type"]], [0, "sandy"])
	assert_false(view.next_day_btn.disabled, "actions enabled once laid out")


func test_default_scenario_renders_as_before() -> void:
	# Both the placeholder (no hand-over) and the backend's default layout.
	for view: Node3D in [_enter(""), _enter("g", _game(ScenarioCatalog.default_patches()))]:
		var soils := ["sandy", "sandy", "organic", "organic", "clay", "clay"]
		assert_eq(_band(view, "soil_type"), soils)
		assert_eq(_band(view, "patch_idx"), [0, 0, 1, 1, 2, 2])
		var tex: Texture2D = view._tile_materials[35].get_shader_parameter("albedo_texture")
		assert_eq(tex.resource_path, FarmLayout.SOIL_TEXTURES["clay"]["albedo"])


func test_two_patches_sharing_a_soil_map_by_index() -> void:
	# Mapping by soil name would give every tile the last patch's data (#516).
	var view := _enter("g", _game([_patch("loam_temperate"), _patch("loam_temperate")]))
	var maize := {"crop_key": "maize", "crop_stage": "vegetative", "lai": 1.0}
	var rice := {"crop_key": "rice", "crop_stage": "vegetative", "lai": 3.0}
	view._apply_patch_data({"field_1": [maize, rice]})
	assert_eq(_band(view, "crop_key"), ["maize", "maize", "maize", "rice", "rice", "rice"])
	assert_eq(_band(view, "lai"), [1.0, 1.0, 1.0, 3.0, 3.0, 3.0])
	assert_eq(view._daily_history.keys(), ["field_1/0", "field_1/1"], "one history per patch")
	# Plant and Harvest send the tile's own patch: 0 from column 0, 1 from column
	# 5. A soil-name lookup gives the same index for both bands and fails here.
	# Both name field_1, the only field the view renders (#548).
	var api: ApiStub = view._api_client
	for case: Array in [[0, 0], [5, 1]]:
		view._select_tile(case[0], 0)
		view._on_crop_selected(FarmView.AVAILABLE_CROPS.find("sorghum"))
		var plant := {"crop_key": "sorghum", "patch_idx": case[1]}
		var plant_call := ["action", "field_1", "plant", plant]
		assert_eq(api.calls[-1], plant_call, "plant from column %d" % case[0])
		view._on_harvest_pressed()
		assert_eq(api.calls[-1], ["action", "field_1", "harvest", {"patch_idx": case[1]}])
	# Completion touches band 1 only.
	view._on_plant_complete(true, {}, "sorghum", "field_1", 1)
	assert_eq(_band(view, "crop_key"), ["maize", "maize", "maize", "sorghum", "sorghum", "sorghum"])


func test_missing_game_returns_to_title_without_creating_one() -> void:
	var view := _enter("gone", [], true)
	var changes: Array = []
	view._change_scene = func(path: String) -> void: changes.append(path)
	view._title_delay_s = 0.0
	var api: ApiStub = view._api_client
	api.reply_game(false, {"not_found": true})
	assert_eq(view.status_label.text, "Game not found, returning to title")
	assert_eq([view._game_id, GameState.game_id], ["", ""])
	assert_true(view.next_day_btn.disabled, "no actions on a missing game")
	await wait_frames(3)
	assert_eq(changes, ["res://scenes/main.tscn"])
	assert_eq(api.calls, [["get_game", "gone"]], "no replacement game")


## Chain `chain`'s reply for ACTIONS[i]. cost_credits encodes both,
## irrigate 11/21, fertilize 12/22, tillage 13/23, lime 14/24. The older chain
## of each overlapping pair (odd) is unaffordable and the newer (even) is
## affordable, so a stale reply also shows in the tooltip, `disabled` and balance.
func _preview_reply(chain: int, i: int) -> Dictionary:
	var code: int = 10 * chain + i + 1
	var newer: bool = chain % 2 == 0
	var balance: int = 1000 + code if newer else code - 1
	return {"cost_credits": code, "balance_credits": balance, "affordable": newer}


## No button may show a code whose last digit belongs to another action.
func _assert_own_codes(view: Node3D, after: String) -> void:
	var price := RegEx.create_from_string("(\\d+)cr\\)$")
	for i in range(ActionPreviews.ACTIONS.size()):
		var btn: Button = view._previews.button_for(ActionPreviews.ACTIONS[i]["action"])
		var found := price.search(btn.text)
		if found != null:
			assert_eq(int(found.get_string(1)) % 10, i + 1, "%s after %s" % [btn.text, after])


## Start chain `older` and answer its first preview, start chain `older + 1`
## while the second is in flight (a fast second Next Day), then answer every
## remaining preview one at a time, checking the buttons after each reply.
func _overlap_two_refreshes(view: Node3D, api: ApiClientTest.PreviewStubClient, older: int) -> void:
	view._refresh_action_costs()
	api.resolve(_preview_reply(older, 0))
	view._refresh_action_costs()
	# The remaining replies in FIFO order, as [chain offset, action index].
	for reply: Array in [[0, 1], [1, 0], [0, 2], [1, 1], [0, 3], [1, 2], [1, 3]]:
		var chain: int = older + reply[0]
		api.resolve(_preview_reply(chain, reply[1]))
		_assert_own_codes(view, "reply %d" % (10 * chain + reply[1] + 1))


func _assert_chain_shown(view: Node3D, chain: int) -> void:
	for i in range(ActionPreviews.ACTIONS.size()):
		var spec: Dictionary = ActionPreviews.ACTIONS[i]
		var btn: Button = view._previews.button_for(spec["action"])
		var code: int = 10 * chain + i + 1
		var label := ActionCost.format_button_label(
			spec["label"], code, spec.get("variable_cost", false)
		)
		assert_eq(btn.text, label, "chain %d's price" % chain)
		assert_eq(btn.tooltip_text, ActionCost.tooltip_text(spec["action"], code, 1000 + code))
		assert_false(btn.disabled, "%s enabled by chain %d's reply" % [spec["label"], chain])
	assert_eq(view._balance_credits, 1000 + 10 * chain + 4, "balance from the last reply")


func test_overlapping_cost_refreshes_keep_each_price_on_its_own_button() -> void:
	# #523 AC6: Next Day twice in quick succession starts a second preview chain
	# while the first is in flight. Each reply must land on its own action's
	# button, and once both chains finish the newest one's prices must show.
	GameState.game_id = ""  # no hand-over, so _ready fetches nothing
	var api: ApiClientTest.PreviewStubClient = ApiClientTest.PreviewStubClient.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._game_id = "g"
	# Two rounds: the queue drains completely and behaves the same next time.
	for older: int in [1, 3]:
		_overlap_two_refreshes(view, api, older)
		_assert_chain_shown(view, older + 1)
	# Each reply answered the preview then in flight, so this order is what
	# makes the chain numbers encoded in the replies true.
	var order := [
		"irrigate", "fertilize", "irrigate", "tillage", "fertilize", "lime", "tillage", "lime"
	]
	assert_eq(api.sent.map(func(s: Array) -> String: return s[0]), order + order, "FIFO")
	assert_eq(api.overlapping_sends, 0, "one preview in flight at a time")


func test_unreachable_backend_stays_without_new_game() -> void:
	var view := _enter("g", [false, {}])
	assert_string_contains(view.status_label.text, "could not load game g")
	assert_eq(view._game_id, "g", "the handed-over id is kept")
	assert_true(view.next_day_btn.disabled, "no actions without a layout")
	var api: ApiStub = view._api_client
	assert_eq(api.calls, [["get_game", "g"]])


## A farm view on game "g" over StubClient: the real client and its queues,
## every transport stubbed (#534).
func _stub_view() -> Node3D:
	GameState.game_id = ""  # no hand-over, so _ready fetches nothing
	var api: ApiClientTest.StubClient = ApiClientTest.StubClient.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._game_id = "g"
	return view


## Select tile (0, 0), patch 0, with a standing crop on it.
func _select_crop(view: Node3D) -> void:
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 2
	view._select_tile(0, 0)


## All nine bar buttons are disabled; then press each one that sends at once
## if it is enabled after all, as a player clicking it would.
func _assert_held(view: Node3D, after: String) -> void:
	for btn: String in _BAR:
		assert_true(view.get(btn).disabled, "%s disabled after %s" % [btn, after])
	for btn: String in _SENDING:
		var button: Button = view.get(btn)
		if not button.disabled:
			button.pressed.emit()


## Land everything that can arrive while a /step or /action is in flight, and
## check the bar after each: the previews and forecast left from the last day
## (affordable and not), a report reply, and a tile deselection and selection.
func _land_mid_flight(view: Node3D, api: ApiClientTest.StubClient, when: String) -> void:
	_assert_held(view, when)
	var n := 0
	while api.awaiting("preview") and n < 8:
		var reply := {"cost_credits": 5, "balance_credits": 900, "affordable": n % 2 == 0}
		api.reply_ok("preview", reply)
		n += 1
		_assert_held(view, "%s, preview reply %d" % [when, n])
	for endpoint: String in ["forecast", "report"]:
		if api.awaiting(endpoint):
			api.reply_ok(endpoint, {})
			_assert_held(view, "%s, %s reply" % [when, endpoint])
	view._deselect()
	_assert_held(view, "%s, deselect" % when)
	_select_crop(view)
	_assert_held(view, "%s, select" % when)


func test_bar_stays_held_until_each_step_and_action_is_applied() -> void:
	# #534 AC5/AC6: a preview reply landing mid-step re-enabled Irrigate,
	# Fertilize, Tillage and Lime, and a tile selection Harvest; an action held
	# no button at all, so a second action or step could overlap it.
	var view := _stub_view()
	var api: ApiClientTest.StubClient = view._api_client
	_select_crop(view)
	# Each send path as [label, its button, the press, the replies it awaits].
	var paths: Array = [
		["Next Day", view.next_day_btn, view._on_next_day, ["step"]],
		["FF7", view.ff7_btn, view._on_ff7, ["step"]],
		["Run", view.ff_all_btn, view._on_ff_all, ["step"]],
		["Irrigate", view.irrigate_btn, view._on_irrigate, ["action", "step"]],
		["Fertilize", view.fertilize_btn, view._on_fertilizer_selected.bind(0), ["action", "step"]],
		["Tillage", view.tillage_btn, view._on_tillage, ["action", "step"]],
		["Lime", view.lime_btn, view._on_lime_selected.bind(2000.0, 10), ["action", "step"]],
		["Plant", view.plant_btn, view._on_crop_selected.bind(0), ["action", "step"]],
		["Harvest", view.harvest_btn, view._on_harvest_pressed, ["action"]],
		["Next Day after Harvest", view.next_day_btn, view._on_next_day, ["step"]],
	]
	var expected: Array = []
	for path: Array in paths:
		var label: String = path[0]
		var button: Button = path[1]
		assert_false(button.disabled, "%s can be pressed" % label)
		var press: Callable = path[2]
		press.call()
		for endpoint: String in path[3]:
			_land_mid_flight(view, api, "%s, awaiting its %s" % [label, endpoint])
			api.reply_ok(endpoint, _REPLY[endpoint])
			expected.append(endpoint)
		assert_false(view.next_day_btn.disabled, "%s: the bar lifts once applied" % label)
	var mutating: Array = api.sends.filter(func(s: Array) -> bool: return s[0] in _REPLY)
	assert_eq(mutating.map(func(s: Array) -> String: return s[0]), expected, "nothing extra sent")
	assert_eq(api.mutating_overlaps, 0, "never two of /step and /action in flight")
	# #548: every action, cost preview and forecast those presses sent named field_1.
	var named: Dictionary = {"action": [], "preview": [], "forecast": []}
	for s: Array in api.sends:
		if s[0] == "forecast":
			named["forecast"].append(s[1].get_slice("?field_id=", 1))
		elif s[0] in named:
			named[s[0]].append(JSON.parse_string(s[3])["field_id"])
	for endpoint: String in named:
		var ids: Array = named[endpoint]
		assert_gt(ids.size(), 0, "%s sent" % endpoint)
		assert_eq(ids.filter(func(f: String) -> bool: return f != "field_1"), [], endpoint)
	# AC7: once the last day's cost refresh is answered, each priced button
	# follows its own reply, against the mid-flight pattern, and Harvest the tile.
	var affordable := [false, true, false, true]
	for ok: bool in affordable:
		api.reply_ok("preview", {"cost_credits": 5, "balance_credits": 900, "affordable": ok})
	for i in range(affordable.size()):
		var btn: Button = view._previews.button_for(ActionPreviews.ACTIONS[i]["action"])
		assert_eq(btn.disabled, not affordable[i], "%s follows its latest reply" % btn.name)
	assert_false(view.harvest_btn.disabled, "Harvest follows the standing crop")
	view._deselect()
	assert_true(view.harvest_btn.disabled, "and the empty selection")


func test_a_failed_step_or_action_lifts_the_bar() -> void:
	# #534 AC8: a transport error, a non-200 or a rejected send lifts the bar
	# and shows the failure; nothing stays locked.
	var presses: Array = [
		["_on_next_day", "step", "Step failed — backend error"],
		["_on_ff_all", "step", "Season failed — backend error"],
		["_on_irrigate", "action", "Action failed"],
		["_on_crop_selected", "action", "Plant failed"],
		["_on_harvest_pressed", "action", "Harvest failed"],
	]
	for failure: String in ["transport", "non-200", "rejected send"]:
		for press: Array in presses:
			var view := _stub_view()
			var api: ApiClientTest.StubClient = view._api_client
			_select_crop(view)
			var endpoint: String = press[1]
			if failure == "rejected send":
				api.send_errors_for[endpoint] = [ERR_CANT_CONNECT]
			var method: String = press[0]
			if method == "_on_crop_selected":
				view.call(method, 0)
			else:
				view.call(method)
			if failure == "transport":
				api.reply(endpoint, HTTPRequest.RESULT_CANT_CONNECT, 0, "")
			elif failure == "non-200":
				api.reply(endpoint, HTTPRequest.RESULT_SUCCESS, 500, "{}")
			var case := "%s, %s" % [method, failure]
			assert_eq(view.status_label.text, press[2], case)
			for btn: String in _BAR:
				assert_false(view.get(btn).disabled, "%s enabled again after %s" % [btn, case])
