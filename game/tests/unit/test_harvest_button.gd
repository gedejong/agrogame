extends GutTest
## Verifies the Harvest ActionBar button → api_client wiring (#316):
## enable/disable gating on crop presence and the execute_action("harvest") call.

const FarmViewScene = preload("res://scenes/farm_view.tscn")

var _auto_cutaway: bool


## Spy that records execute_action calls in place of the real ApiClient.
##
## Models the REAL harvest contract: the `harvest` action response itself
## carries the settlement (grain + revenue + profit), because the backend
## `execute_action` harvest branch settles the season inline. `get_report`
## can be toggled to return the historical 400/failure case (mid-season
## report unavailable) so the failure-handling path is exercised.
class ApiClientSpy:
	extends Node

	var last_action: String = ""
	var last_params: Dictionary = {}
	var last_game_id: String = ""
	var last_field_id: String = ""
	var action_calls: int = 0
	var report_calls: int = 0

	func execute_action(
		game_id: String, field_id: String, action: String, params: Dictionary, callback: Callable
	) -> void:
		action_calls += 1
		last_game_id = game_id
		last_field_id = field_id
		last_action = action
		last_params = params
		# Real harvest response: cost charged, crop settled, P&L returned.
		(
			callback
			. call(
				true,
				{
					"action": action,
					"cost_credits": 50,
					"balance_credits": 9950,
					"grain_g_m2": 120.0,
					"revenue_credits": 1200,
					"profit_credits": 400,
					"harvest_product": "grain",
					"date": "2024-10-18",
					"settlements":
					[
						{
							"crop_key": "maize",
							"product": "grain",
							"area_ha": 0.334,
							"dry_kg_ha": 1200.0,
							"dry_matter_fraction": 1.0,
							"sold_kg": 400.8,
							"quarter": 4,
							"base_credits_per_kg": 0.22,
							"seasonal_multiplier": 1.2,
							"price_credits_per_kg": 0.264,
							"revenue_credits": 1200,
						}
					],
				}
			)
		)

	func get_report(_game_id: String, callback: Callable) -> void:
		report_calls += 1
		callback.call(true, {"revenue_credits": 1200, "profit_credits": 400})


func before_each() -> void:
	# The debug demo driver would create a game from _ready, before the spy is
	# in, contacting the backend and holding the bar until it answers (#534).
	_auto_cutaway = ProjectSettings.get_setting("agrogame/debug/auto_cutaway", false)
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", false)


func after_each() -> void:
	ProjectSettings.set_setting("agrogame/debug/auto_cutaway", _auto_cutaway)


func _make_view() -> Node3D:
	var view: Node3D = FarmViewScene.instantiate()
	add_child_autofree(view)
	# Replace the real HTTP client with a spy and pretend a game already exists
	# so _ensure_game() short-circuits (no backend contact in tests).
	var spy := ApiClientSpy.new()
	add_child_autofree(spy)
	view._api_client = spy
	view._game_id = "test-game"
	return view


func test_harvest_button_present_and_disabled_by_default() -> void:
	var view := _make_view()
	assert_not_null(view.harvest_btn, "Harvest button node resolved")
	assert_true(view.harvest_btn.disabled, "Harvest disabled with no selection")
	assert_ne(view.harvest_btn.tooltip_text, "", "Disabled button has a tooltip")


func test_harvest_disabled_on_bare_patch() -> void:
	var view := _make_view()
	# Select a tile that has no crop.
	view._tile_data[0]["crop_key"] = ""
	view._tile_data[0]["crop_stage"] = 0
	view._select_tile(0, 0)
	assert_true(view.harvest_btn.disabled, "Harvest disabled on bare patch")
	assert_string_contains(view.harvest_btn.tooltip_text, "No standing crop")


func test_harvest_enabled_with_standing_crop() -> void:
	var view := _make_view()
	var idx := 0
	view._tile_data[idx]["crop_key"] = "maize"
	view._tile_data[idx]["crop_stage"] = 2
	view._select_tile(0, 0)
	assert_false(view.harvest_btn.disabled, "Harvest enabled with a standing crop")
	assert_true(view._selected_has_standing_crop(), "Helper reports a standing crop")


func test_harvest_press_calls_execute_action() -> void:
	var view := _make_view()
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 3
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	var spy: ApiClientSpy = view._api_client
	assert_eq(spy.action_calls, 1, "execute_action called once")
	assert_eq(spy.last_action, "harvest", "Action is 'harvest'")
	assert_eq(spy.last_game_id, "test-game", "Passes the current game id")
	assert_eq(spy.last_field_id, "field_1", "Names the field the view renders (#548)")
	assert_true(spy.last_params.has("patch_idx"), "Sends target patch_idx")


func test_harvest_clears_crop_and_surfaces_pnl() -> void:
	var view := _make_view()
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 3
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	var spy: ApiClientSpy = view._api_client
	# Completion callback fired synchronously by the spy.
	assert_eq(view._tile_data[0]["crop_key"], "", "Crop cleared after harvest")
	assert_eq(view._tile_data[0]["crop_stage"], 0, "Crop stage reset after harvest")
	assert_true(view.harvest_btn.disabled, "Harvest re-disabled once crop is gone")
	# P&L comes from the harvest action response itself (real contract).
	assert_string_contains(view.status_label.text, "revenue")
	assert_string_contains(view.status_label.text, "profit")
	assert_eq(spy.report_calls, 0, "no /report after a Harvest (#601)")


func test_harvest_status_line_shows_net_and_the_yield_is_on_the_receipt() -> void:
	# #631 C4: the line names crop, product, net and farm profit and never g/m²
	# (it called fruit "grain"); the yield (#359) moved to the receipt, in t/ha.
	var view := _make_view()
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 3
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	var line: String = view.status_label.text
	assert_string_contains(line, "maize grain")
	assert_string_contains(line, "net 1150")
	assert_string_contains(line, "farm profit 400")
	assert_false(line.contains("g/m"), "no g/m² in the line")
	var receipt: Node = view.get_node("UILayer/HarvestReceipt")
	assert_not_null(receipt, "the receipt opens after a Harvest")
	var text := ""
	for label: Label in receipt.find_children("*", "Label", true, false):
		text += label.text + "\n"
	assert_string_contains(text, "1.20 t/ha")
	assert_string_contains(text, "Field 1")


func test_harvest_names_the_field_and_labels_profit_as_the_farms() -> void:
	# #601 AC4/AC5: profit_credits is the farm-wide season figure, so the line
	# says so, and it names the field harvested. No /report follows: on main a
	# field_2 Harvest then sold field_1's standing maize at grain fill.
	var view := _make_view()
	var spy: ApiClientSpy = view._api_client
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 3
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	assert_string_contains(view.status_label.text, "Field 1")
	assert_string_contains(view.status_label.text, "farm profit 400")
	assert_eq(spy.report_calls, 0, "the harvest never calls /report")


func test_harvest_noop_on_bare_patch() -> void:
	var view := _make_view()
	view._tile_data[0]["crop_key"] = ""
	view._tile_data[0]["crop_stage"] = 0
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	var spy: ApiClientSpy = view._api_client
	assert_eq(spy.action_calls, 0, "No action dispatched on a bare patch")
