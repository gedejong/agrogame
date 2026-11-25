class_name FarmViewHistory
extends RefCounted
## Builds the per-patch daily history used by the sparkline (tile-info)
## panel. Pure data transforms over API step payloads — no scene coupling — so
## it lives outside farm_view.gd (keeping it under the gdlint file-length cap).
##
## History is keyed by (field, patch), as FarmLayout.patch_key gives it: never
## by soil name, which two patches may share (#516), nor by patch index alone,
## which every field has (#600). Each value is an Array[Dictionary] of daily
## records, capped at MAX_HISTORY_DAYS (oldest dropped first).
##
## `water` and `root_zone` are the Quick Status Water and Root zone gauges on
## their 0-100 scale (#669): 100 x the day's Ks, the last WaterStressComputed
## (100 when absent), and 100 x the root-zone water fraction capped at 1.

const MAX_HISTORY_DAYS := 365


static func append_snapshots(snapshots: Array, daily_history: Dictionary, fields: Array) -> void:
	## Append lightweight per-day snapshots (one per field and patch) to the
	## history dict. A snapshot whose field or patch is not in `fields` (the
	## laid-out [{field_id, patches}]) is skipped.
	for snap: Dictionary in snapshots:
		var key := _laid_out_key(fields, snap.get("field_id", ""), snap.get("patch_idx", 0))
		if key.is_empty():
			continue
		if not daily_history.has(key):
			daily_history[key] = []
		(
			daily_history[key]
			. append(
				{
					"crop_stage": snap.get("crop_stage", ""),
					"lai": snap.get("lai", 0.0),
					"root_depth_cm": snap.get("root_depth_cm", 0.0),
					"grain_g_m2": snap.get("grain_g_m2", 0.0),
					"water": _water_gauge(snap.get("events", [])),
					"root_zone": _root_zone_gauge(snap),
					"theta_surface": snap.get("soil_theta_surface", 0.0),
					"n_available": snap.get("n_available_total", 0.0),
					"redox_eh_surface": snap.get("redox_eh_surface", 400.0),
					"fe_available_surface": snap.get("fe_available_surface", 10.0),
					"zn_available_surface": snap.get("zn_available_surface", 1.2),
					"mn_available_surface": snap.get("mn_available_surface", 18.0),
					"agg_mwd_surface": snap.get("agg_mwd_surface", 1.0),
				}
			)
		)
		_cap(daily_history[key])


static func append_patch(
	patch: Dictionary, field_id: String, patch_idx: int, daily_history: Dictionary
) -> void:
	## Append a full record for `field_id`'s patch `patch_idx` from a step payload.
	if patch_idx < 0:
		return
	var key := FarmLayout.patch_key(field_id, patch_idx)
	if not daily_history.has(key):
		daily_history[key] = []
	var soil_state: Dictionary = patch.get("soil_state", {})
	var no3_arr: Array = soil_state.get("n_no3", [])
	var nh4_arr: Array = soil_state.get("n_nh4", [])
	var n_total: float = 0.0
	for v: float in no3_arr:
		n_total += v
	for v: float in nh4_arr:
		n_total += v
	(
		daily_history[key]
		. append(
			{
				"crop_stage": patch.get("crop_stage", ""),
				"lai": patch.get("lai", 0.0),
				"root_depth_cm": patch.get("root_depth_cm", 0.0),
				"grain_g_m2": patch.get("grain_g_m2", 0.0),
				"water": _water_gauge(patch.get("events", [])),
				"root_zone": _root_zone_gauge(patch),
				"theta_surface": patch.get("soil_theta_surface", 0.0),
				"n_available": n_total,
				"redox_eh_surface": _first_or(soil_state, "redox_eh", 400.0),
				"fe_available_surface": _first_or(soil_state, "fe_available", 10.0),
				"zn_available_surface": _first_or(soil_state, "zn_available", 1.2),
				"mn_available_surface": _first_or(soil_state, "mn_available", 18.0),
				"agg_mwd_surface": _first_or(soil_state, "agg_mwd", 1.0),
			}
		)
	)
	_cap(daily_history[key])


## FarmLayout.patch_key of `field_id`'s patch `patch_idx` when `fields` lays it
## out, else "".
static func _laid_out_key(fields: Array, field_id: String, patch_idx: int) -> String:
	for field: Dictionary in fields:
		if field["field_id"] == field_id and patch_idx >= 0:
			if patch_idx < (field["patches"] as Array).size():
				return FarmLayout.patch_key(field_id, patch_idx)
	return ""


static func _water_gauge(events: Array) -> float:
	return 100.0 * float(FarmTiles.stress_from_events(events)["water_ks"])


static func _root_zone_gauge(day: Dictionary) -> float:
	return 100.0 * clampf(float(day.get("root_zone_water_fraction", 0.0)), 0.0, 1.0)


static func _cap(records: Array) -> void:
	## Drop the oldest record once the series exceeds the retention window.
	if records.size() > MAX_HISTORY_DAYS:
		records.pop_front()


static func _first_or(soil_state: Dictionary, key: String, fallback: float) -> float:
	## Surface-layer value = first depth cell; fall back when the array is absent.
	var arr: Array = soil_state.get(key, [])
	if arr.is_empty():
		return fallback
	return float(arr[0])
