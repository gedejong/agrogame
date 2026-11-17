extends GutTest
## Tests for FarmViewHistory — per-patch daily history record building.

const FarmViewHistoryRef = preload("res://scripts/farm_view_history.gd")

## A three-patch layout; history is keyed by patch index, not soil (#516).
const LAYOUT: Array = [{}, {}, {}]


func test_append_snapshots_records_inverted_water_stress() -> void:
	var history: Dictionary = {}
	var snapshots: Array = [{"patch_idx": 0, "lai": 1.5, "water_stress": 0.8}]
	FarmViewHistoryRef.append_snapshots(snapshots, history, LAYOUT)
	assert_true(history.has(0), "record filed under its patch index")
	var rec: Dictionary = history[0][0]
	assert_almost_eq(rec["lai"], 1.5, 0.001)
	# API water_stress 0.8 (supply/demand) inverts to 0.2 (stress intensity).
	assert_almost_eq(rec["water_stress"], 0.2, 0.001)


func test_append_snapshots_defaults_for_missing_fields() -> void:
	var history: Dictionary = {}
	FarmViewHistoryRef.append_snapshots([{"patch_idx": 1}], history, LAYOUT)
	var rec: Dictionary = history[1][0]
	assert_almost_eq(rec["redox_eh_surface"], 400.0, 0.001)
	assert_almost_eq(rec["agg_mwd_surface"], 1.0, 0.001)


func test_append_snapshots_skips_unknown_patch_idx() -> void:
	var history: Dictionary = {}
	# patch_idx outside the game's layout → skipped.
	FarmViewHistoryRef.append_snapshots([{"patch_idx": 9}], history, LAYOUT)
	FarmViewHistoryRef.append_snapshots([{"patch_idx": -1}], history, LAYOUT)
	assert_eq(history.size(), 0, "unknown patch index adds nothing")


func test_append_snapshots_caps_at_retention_window() -> void:
	var history: Dictionary = {}
	var cap: int = FarmViewHistoryRef.MAX_HISTORY_DAYS
	for day in range(cap + 5):
		FarmViewHistoryRef.append_snapshots([{"patch_idx": 0, "lai": float(day)}], history, LAYOUT)
	assert_eq(history[0].size(), cap, "series capped at MAX_HISTORY_DAYS")
	# Oldest (lai == 0..4) dropped; first surviving record is day 5.
	assert_almost_eq(history[0][0]["lai"], 5.0, 0.001)


func test_append_patch_sums_mineral_nitrogen() -> void:
	var history: Dictionary = {}
	var patch: Dictionary = {
		"crop_stage": "vegetative",
		"lai": 2.0,
		"soil_state": {"n_no3": [3.0, 1.0], "n_nh4": [2.0]},
	}
	FarmViewHistoryRef.append_patch(patch, 2, history)
	var rec: Dictionary = history[2][0]
	assert_almost_eq(rec["n_available"], 6.0, 0.001, "n_no3 + n_nh4 summed")
	assert_eq(rec["crop_stage"], "vegetative")


func test_append_patch_uses_surface_layer_and_fallbacks() -> void:
	var history: Dictionary = {}
	var patch: Dictionary = {
		"water_stress": 1.0,
		"soil_state": {"redox_eh": [123.0, -50.0], "fe_available": []},
	}
	FarmViewHistoryRef.append_patch(patch, 0, history)
	var rec: Dictionary = history[0][0]
	# Surface value = first depth cell.
	assert_almost_eq(rec["redox_eh_surface"], 123.0, 0.001)
	# Empty array → documented fallback.
	assert_almost_eq(rec["fe_available_surface"], 10.0, 0.001)
	# Missing key → documented fallback.
	assert_almost_eq(rec["zn_available_surface"], 1.2, 0.001)


func test_append_patch_negative_index_is_noop() -> void:
	var history: Dictionary = {}
	FarmViewHistoryRef.append_patch({"lai": 1.0}, -1, history)
	assert_eq(history.size(), 0, "negative patch index appends nothing")


func test_append_patch_caps_at_retention_window() -> void:
	var history: Dictionary = {}
	var cap: int = FarmViewHistoryRef.MAX_HISTORY_DAYS
	for _day in range(cap + 3):
		FarmViewHistoryRef.append_patch({"soil_state": {}}, 1, history)
	assert_eq(history[1].size(), cap, "patch series capped at MAX_HISTORY_DAYS")
