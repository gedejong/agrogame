extends GutTest
## The Plant crop popup's seed costs (#525), driven through the farm view and
## PreviewStubClient: the real FIFO preview queue, stubbed transport (#523).

const CropPopupScript = preload("res://scripts/crop_popup.gd")
const FarmView = preload("res://scripts/farm_view.gd")
const FarmViewScene = preload("res://scenes/farm_view.tscn")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")

var _auto_soil_view: bool


func before_each() -> void:
	# The debug demo driver would plant and step on its own; keep the view idle.
	_auto_soil_view = ProjectSettings.get_setting("agrogame/debug/auto_soil_view", false)
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_soil_view", _auto_soil_view)


## A farm view on the default layout (sandy, loam, clay bands = patches 0, 1, 2).
func _view() -> Node3D:
	GameState.game_id = ""  # no hand-over, so _ready fetches nothing
	var api: ApiClientTest.PreviewStubClient = ApiClientTest.PreviewStubClient.new()
	add_child_autofree(api)
	var view: Node3D = FarmViewScene.instantiate()
	view._api_client = api
	add_child_autofree(view)
	view._game_id = "g"
	return view


## Each sent preview as [action, crop_key, patch_idx], -1 for a missing index.
func _sent(api: ApiClientTest.PreviewStubClient) -> Array:
	return api.sent.map(
		func(s: Array) -> Array: return [s[0], s[1]["crop_key"], int(s[1].get("patch_idx", -1))]
	)


func test_one_bare_item_per_crop_with_its_index_as_id() -> void:
	var crops: Array[String] = ["maize", "spring_wheat"]
	var popup := CropPopupScript.new(crops) as CropPopup
	add_child_autofree(popup)
	assert_eq([popup.get_item_text(0), popup.get_item_text(1)], ["Maize", "Spring Wheat"])
	assert_eq([popup.get_item_id(0), popup.get_item_id(1)], [0, 1])


func test_each_crop_shows_its_seed_cost_for_the_selected_patch() -> void:
	# AC7: one /action/preview per crop, in order, with the params a plant from
	# this tile sends. Loam is patch 1 (area 0.334), where grape costs 167.
	var view := _view()
	var api: ApiClientTest.PreviewStubClient = view._api_client
	var popup: CropPopup = view._crop_popup
	view._select_tile(2, 0)
	view._on_plant_pressed()
	var costs := [67, 50, 40, 60, 167]
	for i in range(FarmView.AVAILABLE_CROPS.size()):
		var crop: String = FarmView.AVAILABLE_CROPS[i]
		assert_eq(popup.get_item_text(i), crop.capitalize(), "bare until its reply")
		assert_false(popup.is_item_disabled(i), "selectable until its reply")
		assert_eq(view._plant_params(crop), {"crop_key": crop, "patch_idx": 1}, "as planted")
		if crop == "rice":
			api.respond(HTTPRequest.RESULT_SUCCESS, 500, "")
			continue
		api.resolve({"cost_credits": costs[i], "affordable": crop != "grape"})
	var texts: Array = range(5).map(func(i: int) -> String: return popup.get_item_text(i))
	var labels := ["Maize (67cr)", "Spring Wheat (50cr)", "Sorghum (40cr)", "Rice", "Grape (167cr)"]
	assert_eq(texts, labels, "a failed preview leaves rice bare")
	var disabled: Array = range(5).map(func(i: int) -> bool: return popup.is_item_disabled(i))
	assert_eq(disabled, [false, false, false, false, true], "unaffordable grape greyed out")
	var expected: Array = FarmView.AVAILABLE_CROPS.map(
		func(c: String) -> Array: return ["plant", c, 1]
	)
	assert_eq(_sent(api), expected, "one preview per crop, in order, for patch 1")
	var on_field_1: Array = expected.map(func(_e: Array) -> String: return "field_1")
	assert_eq(api.field_ids, on_field_1, "every preview names field_1 (#548)")


func test_no_game_yet_previews_nothing() -> void:
	var view := _view()
	view._game_id = ""
	view._select_tile(2, 0)
	view._on_plant_pressed()
	var api: ApiClientTest.PreviewStubClient = view._api_client
	assert_eq(api.sent, [])
	assert_eq(view._crop_popup.get_item_text(0), "Maize")


func test_reopening_for_another_patch_never_shows_the_first_patchs_costs() -> void:
	# AC8: open on sandy (patch 0), then on loam (patch 1) before any reply.
	# Sandy's replies (10 + i, unaffordable) come first in FIFO order and must
	# be dropped: after every reply each item is bare or shows loam's 20 + i.
	var view := _view()
	var api: ApiClientTest.PreviewStubClient = view._api_client
	var popup: CropPopup = view._crop_popup
	var n: int = FarmView.AVAILABLE_CROPS.size()
	var one_cycle: Array = []
	for cycle in range(2):  # the queue drains, and the next opening behaves the same
		view._select_tile(0, 0)
		view._on_plant_pressed()
		view._select_tile(2, 0)
		view._on_plant_pressed()
		for reply in range(2 * n):
			var loam: bool = reply >= n
			one_cycle.append(1 if loam else 0)
			api.resolve({"cost_credits": (20 if loam else 10) + reply % n, "affordable": loam})
			for i in range(n):
				var label: String = FarmView.AVAILABLE_CROPS[i].capitalize()
				if loam and i <= reply % n:
					label = ActionCost.format_button_label(label, 20 + i)
				assert_eq(popup.get_item_text(i), label, "cycle %d reply %d" % [cycle, reply])
				assert_false(popup.is_item_disabled(i), "cycle %d reply %d" % [cycle, reply])
	var patches: Array = _sent(api).map(func(s: Array) -> int: return s[2])
	assert_eq(patches, one_cycle, "sandy's five, then loam's, twice")
	assert_eq(api.overlapping_sends, 0, "one preview in flight at a time")


func test_plant_cost_replies_never_touch_the_action_buttons() -> void:
	# AC9: a reply landing during a /step must not re-enable the bar (#534).
	var view := _view()
	var api: ApiClientTest.PreviewStubClient = view._api_client
	view._select_tile(4, 0)
	view._on_plant_pressed()
	view._set_buttons_disabled(true)  # a /step is now in flight
	var buttons: Array = [
		view.next_day_btn,
		view.ff7_btn,
		view.ff_all_btn,
		view.irrigate_btn,
		view.fertilize_btn,
		view.tillage_btn,
		view.lime_btn,
		view.plant_btn,
		view.harvest_btn,
	]
	var texts: Array = buttons.map(func(b: Button) -> String: return b.text)
	for i in range(FarmView.AVAILABLE_CROPS.size()):
		api.resolve({"cost_credits": 40, "balance_credits": 9000, "affordable": true})
	assert_eq(view._crop_popup.get_item_text(2), "Sorghum (40cr)", "the replies landed")
	for b: Button in buttons:
		assert_true(b.disabled, "%s still disabled" % b.name)
	assert_eq(buttons.map(func(b: Button) -> String: return b.text), texts, "labels untouched")
	assert_eq(view._balance_credits, -1, "the plant preview sets no balance")
