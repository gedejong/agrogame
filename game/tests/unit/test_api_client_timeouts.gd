extends GutTest
## /step's timeout scales with the days it asks for (#564). Kept apart from
## test_api_client.gd, which is at gdlint's public-method cap; it runs over that
## file's StubClient, the real client with every transport stubbed (#534).

const ApiClientScript = preload("res://scripts/api_client.gd")
const ApiClientTest = preload("res://tests/unit/test_api_client.gd")


## StubClient with every timeout cut 100-fold, so a 1-day /step times out after
## 0.105 s, where the old flat /step timeout would take 1.2 s and Run Season's 1.1 s.
class ShortStepClient:
	extends ApiClientTest.StubClient

	func _timeout_s(endpoint: String) -> float:
		return super(endpoint) / 100.0


func test_step_timeout_scales_with_days_and_other_endpoints_keep_10_s() -> void:
	# #564 AC2: a flat 120 s held the bar two minutes on a hung 1-day Next Day.
	# Now 10 s + 0.5 s/day, so Next Day gives up after 10.5 s. Run Season's 200
	# days get 110 s, 7.5x the 14.7 s measured at 20 fps and 17.7x the 6.2 s at
	# 60 fps (#556, M1 Pro); the backend clamps a /step to its 200-day window, so
	# 110 s is also the ceiling.
	var api: ApiClientTest.StubClient = ApiClientTest.StubClient.new()
	add_child_autofree(api)
	var ignore := func(_ok: bool, _data: Dictionary) -> void: pass
	var cases: Array = [
		[1, 10.5], [7, 13.5], [ApiClientScript.RUN_SEASON_DAYS, 110.0], [400, 110.0]
	]
	for case: Array in cases:
		api.step_day("g", case[0], ignore)
		assert_almost_eq(api._timeout_s("step"), case[1], 1e-9, "%d days" % case[0])
		api.reply_ok("step", {})
	api.run_season("g", ignore)
	assert_almost_eq(api._timeout_s("step"), 110.0, 1e-9, "Run Season")
	assert_gte(api._timeout_s("step"), 7.0 * 14.7, "7x the 200-day step at 20 fps")
	assert_eq(ApiClientScript.TIMEOUT_S["step"], 110.0, "the ceiling")
	for endpoint: String in ApiClientScript._ENDPOINTS:
		if endpoint != "step":
			assert_eq(api._timeout_s(endpoint), 10.0, "%s keeps 10 s" % endpoint)


func test_a_hung_one_day_step_times_out_on_its_own_scaled_timeout() -> void:
	# #564 AC2: the scaled value is the one the send's timer runs on: cut
	# 100-fold, a 1-day /step must give up before Run Season's 1.1 s could pass.
	var api := ShortStepClient.new()
	add_child_autofree(api)
	var got: Array = []
	api.step_day("g", 1, func(ok: bool, _data: Dictionary) -> void: got.append(ok))
	assert_true(await wait_until(func() -> bool: return not got.is_empty(), 0.6), "timed out")
	assert_eq(got, [false], "failed once, on its timeout")
	assert_push_warning("step timed out")
	assert_eq(api.cancels, ["step"], "the hung /step was cancelled")
