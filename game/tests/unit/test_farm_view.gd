extends GutTest

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")

var _auto_cutaway: bool


## Stands in for ApiClient: records calls and answers at once (or on demand,
## with defer_game), so no test touches the network.
class ApiStub:
	extends Node
	var calls: Array = []
	var game_reply: Array = [true, {}]
	var defer_game: bool = false
	var _game_cb: Callable

	func get_game(game_id: String, callback: Callable) -> void:
		calls.append(["get_game", game_id])
		_game_cb = callback
		if not defer_game:
			reply_game(game_reply[0], game_reply[1])

	func reply_game(ok: bool, data: Dictionary) -> void:
		_game_cb.call(ok, data)

	func create_game(callback: Callable, _patches: Array = []) -> void:
		calls.append(["create_game"])
		callback.call(true, {"game_id": "created"})

	func step_day(game_id: String, days: int, _callback: Callable) -> void:
		calls.append(["step_day", game_id, days])

	func execute_action(_id: String, action: String, params: Dictionary, _cb: Callable) -> void:
		calls.append(["action", action, params])


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
	for spec: Dictionary in FarmView._PREVIEW_ACTIONS:
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
	for spec: Dictionary in FarmView._PREVIEW_ACTIONS:
		if spec["action"] == "irrigate":
			assert_eq(spec["params"].get("amount_mm"), 20)


func test_preview_fertilize_is_variable_cost() -> void:
	# Fertilize spans several priced tiers (#349 review), so its spec carries no
	# fixed params: the preview resolves the cheapest tier at request time and
	# the button shows a "from" price, gating only when no tier is affordable.
	for spec: Dictionary in FarmView._PREVIEW_ACTIONS:
		if spec["action"] == "fertilize":
			assert_true(spec.get("variable_cost", false), "fertilize previews a from-price")
			assert_true(spec["params"].is_empty(), "fertilize params resolved dynamically")


func test_preview_lime_is_variable_cost() -> void:
	# Lime is offered in t/ha tiers through its own picker (#465), so like
	# fertilize it previews the cheapest tier as a "from" price rather than a
	# fixed cost.
	for spec: Dictionary in FarmView._PREVIEW_ACTIONS:
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
	assert_eq(view._daily_history.keys(), [0, 1], "one history per patch")
	# Plant and Harvest send the tile's own patch: 0 from column 0, 1 from column
	# 5. A soil-name lookup gives the same index for both bands and fails here.
	var api: ApiStub = view._api_client
	for case: Array in [[0, 0], [5, 1]]:
		view._select_tile(case[0], 0)
		view._on_crop_selected(FarmView.AVAILABLE_CROPS.find("sorghum"))
		var plant := {"crop_key": "sorghum", "patch_idx": case[1]}
		assert_eq(api.calls[-1], ["action", "plant", plant], "plant from column %d" % case[0])
		view._on_harvest_pressed()
		assert_eq(api.calls[-1], ["action", "harvest", {"patch_idx": case[1]}])
	# Completion touches band 1 only.
	view._on_plant_complete(true, {}, "sorghum", 1)
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


## Chain `chain`'s reply for _PREVIEW_ACTIONS[i]. cost_credits encodes both,
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
	for i in range(FarmView._PREVIEW_ACTIONS.size()):
		var btn: Button = view._action_button_for(FarmView._PREVIEW_ACTIONS[i]["action"])
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
	for i in range(FarmView._PREVIEW_ACTIONS.size()):
		var spec: Dictionary = FarmView._PREVIEW_ACTIONS[i]
		var btn: Button = view._action_button_for(spec["action"])
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
