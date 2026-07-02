extends GutTest
## Verifies the Harvest ActionBar button → api_client wiring (#316):
## enable/disable gating on crop presence and the execute_action("harvest") call.

const FarmViewScene = preload("res://scenes/farm_view.tscn")


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
	var action_calls: int = 0
	var report_calls: int = 0
	# When false, get_report reports failure (as a real mid-season 400 would).
	var report_succeeds: bool = true

	func execute_action(
		game_id: String, action: String, params: Dictionary, callback: Callable
	) -> void:
		action_calls += 1
		last_game_id = game_id
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
				}
			)
		)

	func get_report(_game_id: String, callback: Callable) -> void:
		report_calls += 1
		if not report_succeeds:
			callback.call(false, {})
			return
		callback.call(true, {"revenue_credits": 1200, "profit_credits": 400})


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
	# The detailed report is still fetched opportunistically.
	assert_eq(spy.report_calls, 1, "Detailed report fetched after settlement")


func test_harvest_handles_unavailable_report() -> void:
	# Real backend returned HTTP 400 on a mid-season /report before this fix.
	# The action response already surfaced P&L; a report failure must degrade
	# gracefully with a visible note rather than silently swallowing.
	var view := _make_view()
	var spy: ApiClientSpy = view._api_client
	spy.report_succeeds = false
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 3
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	assert_eq(spy.report_calls, 1, "Report fetch attempted")
	# Action-response P&L stays visible; failure appends a clear note.
	assert_string_contains(view.status_label.text, "revenue")
	assert_string_contains(view.status_label.text, "detailed report unavailable")


func test_harvest_noop_on_bare_patch() -> void:
	var view := _make_view()
	view._tile_data[0]["crop_key"] = ""
	view._tile_data[0]["crop_stage"] = 0
	view._select_tile(0, 0)
	view._on_harvest_pressed()
	var spy: ApiClientSpy = view._api_client
	assert_eq(spy.action_calls, 0, "No action dispatched on a bare patch")
