class_name StressUtils
extends RefCounted
## Shared stress parsing for crop visualization.
## Converts tile_data stress fields into per-type continuous floats.

## Stress keys used throughout the visualization pipeline.
const STRESS_KEYS: Array[String] = ["water", "n", "p", "fe", "zn", "frost", "heat"]

## Maximum geometry size reduction from Zn deficiency (30%).
## Ref: Marschner 2012 — Zn-deficient cereals show "little leaf" + shortened internodes.
const ZN_STUNT_MAX: float = 0.3


static func parse_stress_data(tile_data: Dictionary) -> Dictionary:
	"""Extract per-type stress values from tile_data.

	Returns {water, n, p, fe, zn, frost, heat} as floats in [0, 1]
	(0 = no stress, 1 = severe). Frost/heat are transient damage
	flags — wired from FrostDamageApplied / HeatDamageApplied events.
	Note: water_stress is wired end-to-end. Nutrient stress keys
	(n_stress, p_stress, fe_stress, zn_stress) require API exposure
	of per-nutrient stress factors — TODO in a follow-up issue.
	"""
	var water: float = _clamp01(1.0 - tile_data.get("water_stress", 1.0))
	var n_stress: float = _clamp01(tile_data.get("n_stress", 0.0))
	var p_stress: float = _clamp01(tile_data.get("p_stress", 0.0))
	var fe_stress: float = _clamp01(tile_data.get("fe_stress", 0.0))
	var zn_stress: float = _clamp01(tile_data.get("zn_stress", 0.0))
	var frost: float = _clamp01(tile_data.get("frost_damage", 0.0))
	var heat: float = _clamp01(tile_data.get("heat_damage", 0.0))
	return {
		"water": water,
		"n": n_stress,
		"p": p_stress,
		"fe": fe_stress,
		"zn": zn_stress,
		"frost": frost,
		"heat": heat,
	}


static func calc_stunt_factor(stresses: Dictionary) -> float:
	"""Geometry scale multiplier from Zn deficiency.
	1.0 = full size, 0.7 = 30% reduction.
	Ref: Zn-deficient cereals show ~25-30% height reduction (Marschner 2012)."""
	var zn: float = stresses.get("zn", 0.0)
	return clampf(1.0 - zn * ZN_STUNT_MAX, 1.0 - ZN_STUNT_MAX, 1.0)


static func calc_collapse_factor(senescence: float) -> float:
	"""Vertical scale for dead/senesced plants. Plants 'fall over'
	as senescence approaches 1.0. Returns Y scale multiplier."""
	# Collapse onsets at 0.85, full collapse at 1.0 → 40% of original height.
	var t: float = clampf((senescence - 0.85) / 0.15, 0.0, 1.0)
	return lerpf(1.0, 0.4, t)


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
