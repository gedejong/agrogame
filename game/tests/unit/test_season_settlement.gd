extends GutTest
## Season settlement in the farm view (#518): the /step that completes a season
## settles it server-side, so Harvest is disabled until the next season and the
## status line shows the season's revenue and profit from GET /report.

const FarmViewScene = preload("res://scenes/farm_view.tscn")
const SETTLED := "Season settled: start the next season"


## Stub for the calls a /step response triggers: /report, /forecast, /preview.
class ApiClientStub:
	extends Node

	var report_calls: int = 0
	var report_succeeds: bool = true

	func get_report(_game_id: String, callback: Callable) -> void:
		report_calls += 1
		if not report_succeeds:
			callback.call(false, {})
			return
		callback.call(true, {"revenue_credits": 697, "profit_credits": 497})

	func get_forecast(_game_id: String, _callback: Callable) -> void:
		pass

	func preview_action(
		_game_id: String, _action: String, _params: Dictionary, _callback: Callable
	) -> void:
		pass


func _make_view() -> Node3D:
	var view: Node3D = FarmViewScene.instantiate()
	add_child_autofree(view)
	var stub := ApiClientStub.new()
	add_child_autofree(stub)
	view._api_client = stub
	view._game_id = "test-game"
	# A selected standing crop, so only settlement can disable Harvest.
	view._tile_data[0]["crop_key"] = "maize"
	view._tile_data[0]["crop_stage"] = 3
	view._select_tile(0, 0)
	return view


func _step(complete: bool) -> Dictionary:
	return {
		"day_number": 150,
		"date": "2024-08-29",
		"weather": {},
		"patches": {},
		"balance_credits": 10497,
		"season_complete": complete,
	}


func test_observe_step_tracks_season_complete() -> void:
	var s := SeasonSettlement.new()
	assert_true(s.observe_step({"season_complete": true}), "completed season reported")
	assert_true(s.settled, "settled after a completing step")
	assert_false(s.observe_step({"season_complete": false}), "next season under way")
	assert_false(s.settled, "unsettled once a step reports an open season")
	assert_false(s.observe_step({}), "missing flag reads as an open season")


func test_harvest_button_states() -> void:
	var s := SeasonSettlement.new()
	var btn := Button.new()
	autofree(btn)
	s.apply_harvest_button(btn, true, true)
	assert_false(btn.disabled, "standing crop, open season: enabled")
	assert_eq(btn.tooltip_text, "Harvest the standing crop on this patch")
	s.apply_harvest_button(btn, false, true)
	assert_true(btn.disabled, "bare patch: disabled")
	assert_eq(btn.tooltip_text, "No standing crop to harvest on this patch")
	s.apply_harvest_button(btn, false, false)
	assert_eq(btn.tooltip_text, "Select a patch with a standing crop to harvest")
	s.settled = true
	s.apply_harvest_button(btn, true, true)
	assert_true(btn.disabled, "settled season: disabled even over a standing crop")
	assert_eq(btn.tooltip_text, SETTLED)


func test_report_text() -> void:
	var report := {"revenue_credits": 543, "profit_credits": 343}
	assert_eq(
		SeasonSettlement.report_text(true, report),
		"Season complete: revenue 543, profit 343 credits"
	)
	assert_eq(SeasonSettlement.report_text(false, {}), "Season complete")


func test_completing_step_disables_harvest_and_shows_report() -> void:
	var view := _make_view()
	var stub: ApiClientStub = view._api_client
	assert_false(view.harvest_btn.disabled, "Harvest enabled before completion")
	view._on_step_complete(true, _step(true))
	assert_true(view.harvest_btn.disabled, "Harvest disabled after completion")
	assert_eq(view.harvest_btn.tooltip_text, SETTLED)
	assert_eq(stub.report_calls, 1, "season report fetched once")
	assert_eq(view.status_label.text, "Season complete: revenue 697, profit 497 credits")
	view._set_buttons_disabled(false)
	assert_true(view.harvest_btn.disabled, "re-enabling the bar keeps Harvest off")


func test_report_failure_falls_back() -> void:
	var view := _make_view()
	var stub: ApiClientStub = view._api_client
	stub.report_succeeds = false
	view._on_step_complete(true, _step(true))
	assert_eq(view.status_label.text, "Season complete")


func test_open_season_step_re_enables_harvest() -> void:
	var view := _make_view()
	var stub: ApiClientStub = view._api_client
	view._on_step_complete(true, _step(true))
	view._on_step_complete(false, {})
	assert_true(view.harvest_btn.disabled, "a failed step does not unsettle")
	view._on_step_complete(true, _step(false))
	assert_false(view.harvest_btn.disabled, "next season: Harvest enabled again")
	assert_eq(stub.report_calls, 1, "no report for an open-season step")


func test_run_season_keeps_report_status() -> void:
	var view := _make_view()
	view._on_season_complete(true, _step(true))
	assert_eq(view.status_label.text, "Season complete: revenue 697, profit 497 credits")
	view._on_season_complete(false, {})
	assert_eq(view.status_label.text, "Season failed — backend error")
	assert_true(view.harvest_btn.disabled, "still settled after a failed run")
