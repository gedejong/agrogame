extends GutTest

const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")

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
	# Plant and Harvest from column 5 target patch 1; completion touches band 1 only.
	var api: ApiStub = view._api_client
	view._select_tile(5, 0)
	view._on_crop_selected(FarmView.AVAILABLE_CROPS.find("sorghum"))
	assert_eq(api.calls[-1], ["action", "plant", {"crop_key": "sorghum", "patch_idx": 1}])
	view._on_harvest_pressed()
	assert_eq(api.calls[-1], ["action", "harvest", {"patch_idx": 1}])
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


func test_unreachable_backend_stays_without_new_game() -> void:
	var view := _enter("g", [false, {}])
	assert_string_contains(view.status_label.text, "could not load game g")
	assert_eq(view._game_id, "g", "the handed-over id is kept")
	assert_true(view.next_day_btn.disabled, "no actions without a layout")
	var api: ApiStub = view._api_client
	assert_eq(api.calls, [["get_game", "g"]])
