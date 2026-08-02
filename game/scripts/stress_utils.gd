class_name StressUtils
extends RefCounted
## Shared stress parsing for crop visualization.
## Converts tile_data stress fields into per-type continuous floats.

## Stress keys used throughout the visualization pipeline.
const STRESS_KEYS: Array[String] = ["water", "n", "p", "fe", "zn", "frost", "heat"]

## Maximum geometry size reduction from Zn deficiency (30%).
## Ref: Marschner 2012 — Zn-deficient cereals show "little leaf" + shortened internodes.
const ZN_STUNT_MAX: float = 0.3

## Lodging onset thresholds (#273). Severe drought only lodges a plant once
## senescence is advanced; near-total senescence lodges on its own.
## A `water` stress > 0.8 corresponds to water availability < 0.2.
const LODGE_WATER_STRESS_MIN: float = 0.8
const LODGE_SENESCENCE_MIN: float = 0.7
const LODGE_SENESCENCE_ONLY: float = 0.95


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


static func calc_lodging_factor(stresses: Dictionary, senescence: float) -> float:
	"""Stem-lodging severity in [0, 1] for lean/tilt under severe stress.
	0 = upright, 1 = fully lodged. Real cereals lodge (stems bend, the plant
	leans) under severe combined stress; near-dead plants lean regardless of
	water. `stresses['water']` is stress severity (1 = severe drought, i.e.
	water availability < 0.2 ⟺ water stress > 0.8).
	Ref: Berry et al. 2004, Field Crops Research — cereal lodging mechanics."""
	var water_stress: float = clampf(stresses.get("water", 0.0), 0.0, 1.0)
	var sen: float = clampf(senescence, 0.0, 1.0)
	# Path A — drought lodging: severe water stress during late senescence.
	# Graded product of both over-threshold amounts → smooth onset (no popping).
	var drought_lodge: float = 0.0
	if water_stress > LODGE_WATER_STRESS_MIN and sen > LODGE_SENESCENCE_MIN:
		var w: float = (water_stress - LODGE_WATER_STRESS_MIN) / (1.0 - LODGE_WATER_STRESS_MIN)
		var d: float = (sen - LODGE_SENESCENCE_MIN) / (1.0 - LODGE_SENESCENCE_MIN)
		drought_lodge = clampf(w, 0.0, 1.0) * clampf(d, 0.0, 1.0)
	# Path B — terminal lodging: near-total senescence lodges on its own.
	var sen_span: float = 1.0 - LODGE_SENESCENCE_ONLY
	var sen_lodge: float = clampf((sen - LODGE_SENESCENCE_ONLY) / sen_span, 0.0, 1.0)
	return clampf(maxf(drought_lodge, sen_lodge), 0.0, 1.0)


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
