class_name StressUtils
extends RefCounted
## Shared stress parsing for crop visualization.
## Converts tile_data stress fields into per-type continuous floats.

## Stress keys used throughout the visualization pipeline.
const STRESS_KEYS: Array[String] = ["water", "n", "p", "fe", "zn"]


static func parse_stress_data(tile_data: Dictionary) -> Dictionary:
	"""Extract per-type stress values from tile_data.

	Returns {water: float, n: float, p: float, fe: float, zn: float}.
	Values are continuous 0.0 (no stress) to 1.0 (severe).
	Note: water_stress is wired end-to-end. Nutrient stress keys
	(n_stress, p_stress, fe_stress, zn_stress) require API exposure
	of per-nutrient stress factors — TODO in a follow-up issue.
	"""
	var water: float = _clamp01(1.0 - tile_data.get("water_stress", 1.0))
	var n_stress: float = _clamp01(tile_data.get("n_stress", 0.0))
	var p_stress: float = _clamp01(tile_data.get("p_stress", 0.0))
	var fe_stress: float = _clamp01(tile_data.get("fe_stress", 0.0))
	var zn_stress: float = _clamp01(tile_data.get("zn_stress", 0.0))
	return {"water": water, "n": n_stress, "p": p_stress, "fe": fe_stress, "zn": zn_stress}


static func dominant_stress(stresses: Dictionary) -> String:
	"""Return key of highest stress value. Ties broken by STRESS_KEYS order."""
	var best_key: String = "water"
	var best_val: float = 0.0
	for key: String in STRESS_KEYS:
		var val: float = stresses.get(key, 0.0)
		if val > best_val:
			best_val = val
			best_key = key
	return best_key


static func _clamp01(v: float) -> float:
	return clampf(v, 0.0, 1.0)
