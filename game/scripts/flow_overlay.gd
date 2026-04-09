class_name FlowOverlay
extends Node3D
## Flow tube network overlay for the soil cutaway.
## Maps simulation events to glass-tube visualizations with animated particles.
## Sits as a child of the cutaway container; updated on each step.

const MAX_TUBES := 20
const HEAVY_RAIN_MM := 5.0
const RAIN_CONNECTOR_MM := 1.0
const PULSE_INTENSITY := 2.5
const PULSE_DURATION := 0.6
const RAIN_SKY_Y := 0.25

## Substance colors — NH4 and NO3 distinct for visible transformations
const COLOR_WATER := Color(0.376, 0.647, 0.980, 0.8)
const COLOR_NO3 := Color(0.290, 0.871, 0.502, 0.8)  # bright green — mobile nitrate
const COLOR_NH4 := Color(0.2, 0.75, 0.75, 0.8)  # teal/cyan — ammonium (held by clay)
const COLOR_ORGANIC_N := Color(0.45, 0.65, 0.35, 0.8)  # olive — locked in organic matter
const COLOR_PHOSPHORUS := Color(0.655, 0.545, 0.980, 0.8)  # #A78BFA
const COLOR_CARBON := Color(0.984, 0.749, 0.141, 0.8)

## Event type -> tube config.
## z_slot: small offset to separate sub-types within same layer.
## Vertical tubes (up/down) at z_slot. Lateral per-layer at z_slot.
const EVENT_CONFIG := {
	"WaterInfiltrated":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "down",
		"mag_key": "amounts_mm_sum",
		"label": "Infiltration",
		"z_slot": -0.35,
	},
	"WaterDrained":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "down",
		"mag_key": "amount_mm",
		"label": "Percolation",
		"z_slot": -0.25,
	},
	"EvaporationTaken":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "up",
		"mag_key": "amount_mm",
		"label": "Evaporation",
		"z_slot": -0.45,
	},
	"TranspirationByLayer":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "up",
		"mag_key": "total_mm",
		"label": "Transpiration",
		"z_slot": -0.35,
	},
	"RunoffGenerated":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "lateral",
		"mag_key": "amount_mm",
		"label": "Runoff",
		"z_slot": -0.45,
		"y_frac": 0.5,
	},
	"NitrificationOccurred":
	{
		"color": COLOR_NH4,
		"substance": "nitrogen",
		"direction": "lateral",
		"mag_key": "amount_kg_ha",
		"label": "NH4 \u2192 NO3",
		"z_slot": 0.18,
		"y_frac": 0.25,
	},
	"MineralizationOccurred":
	{
		"color": COLOR_ORGANIC_N,
		"substance": "nitrogen",
		"direction": "lateral",
		"mag_key": "amount_kg_ha",
		"label": "Org-N \u2192 NH4",
		"z_slot": 0.18,
		"y_frac": 0.7,
	},
	"DenitrificationOccurred":
	{
		"color": COLOR_NO3,
		"substance": "nitrogen",
		"direction": "up",
		"mag_key": "amount_kg_ha",
		"label": "Denitrification",
		"z_slot": 0.2,
	},
	"VolatilizationOccurred":
	{
		"color": COLOR_NH4,
		"substance": "nitrogen",
		"direction": "up",
		"mag_key": "amount_kg_ha",
		"label": "NH3 loss",
		"z_slot": 0.3,
	},
	"NutrientLeached":
	{
		"color": COLOR_NO3,
		"substance": "nitrogen",
		"direction": "down",
		"mag_key": "amount_kg_ha",
		"label": "NO3 leaching",
		"z_slot": -0.15,
	},
	"PhosphorusFixationOccurred":
	{
		"color": COLOR_PHOSPHORUS,
		"substance": "phosphorus",
		"direction": "lateral",
		"mag_key": "amount_fixed_kg_ha",
		"label": "Avail-P \u2192 Fixed-P",
		"z_slot": -0.15,
		"y_frac": 0.25,
	},
	"SOMDecomposed":
	{
		"color": COLOR_CARBON,
		"substance": "carbon",
		"direction": "lateral",
		"mag_key": "decomposed_c_kg_ha",
		"label": "Decomposition",
		"z_slot": -0.15,
		"y_frac": 0.7,
	},
	"CO2Respired":
	{
		"color": COLOR_CARBON,
		"substance": "carbon",
		"direction": "up",
		"mag_key": "co2_c_kg_ha",
		"label": "Soil CO2 \u2191",
		"z_slot": 0.4,
	},
}

var _tubes: Array[Node3D] = []
var _layer_positions: Array[float] = []
var _pillar_pos := Vector3.ZERO

var _prev_configs: Array[Dictionary] = []


func update_from_events(events: Array, profile_layers: Array, pillar_pos: Vector3) -> void:
	## Update tube network with smooth transitions.
	_compute_layer_positions(profile_layers)
	_pillar_pos = pillar_pos
	var new_configs := _events_to_configs(events)
	new_configs.sort_custom(
		func(a: Dictionary, b: Dictionary) -> bool:
			return a.get("magnitude", 0.0) > b.get("magnitude", 0.0)
	)
	var count := mini(new_configs.size(), MAX_TUBES)
	new_configs = new_configs.slice(0, count)
	# Build lookup of old tubes by compound key (label + index)
	var old_by_key: Dictionary = {}
	for i in range(_tubes.size()):
		if i < _prev_configs.size():
			var key: String = _tube_key(_prev_configs[i], i)
			old_by_key[key] = i
	# Match new configs to old tubes
	var matched_old: Array[int] = []
	var new_tubes: Array[Node3D] = []
	for ci in range(new_configs.size()):
		var cfg: Dictionary = new_configs[ci]
		var key: String = _tube_key(cfg, ci)
		if old_by_key.has(key):
			var old_idx: int = old_by_key[key]
			matched_old.append(old_idx)
			var old_tube: FlowTube = _tubes[old_idx] as FlowTube
			old_tube.tween_magnitude(cfg.get("magnitude", 0.5))
			new_tubes.append(old_tube)
		else:
			var tube := FlowTube.create(cfg)
			tube.fade_in()
			_apply_gas_dissipation(tube, cfg)
			add_child(tube)
			new_tubes.append(tube)
	# Fade out unmatched old tubes
	for i in range(_tubes.size()):
		if i not in matched_old:
			var old_tube: FlowTube = _tubes[i] as FlowTube
			old_tube.fade_out()
	_tubes.clear()
	_tubes = new_tubes
	_prev_configs = new_configs
	# Detect pulse events
	_check_pulse_events(events)


func show_test_tubes(pillar_pos := Vector3.ZERO) -> void:
	## Debug: spawn sample tubes of each type for visual testing.
	clear_tubes()
	_layer_positions = [0.0, -0.125, -0.3, -0.5]
	_pillar_pos = pillar_pos
	# Atmospheric tubes on tile surface, soil tubes on cutaway face
	var fx_atmo: float = pillar_pos.x + 0.48
	var fx_soil: float = pillar_pos.x + 0.52
	var fz: float = pillar_pos.z
	# Spread tubes along the Z axis on the face
	# Vertical tubes in a column at the face, spread along Z
	# Lateral tubes run along Z at the face, at layer midpoints
	var l1y: float = (_layer_positions[0] + _layer_positions[1]) * 0.5
	var l2y: float = (_layer_positions[1] + _layer_positions[2]) * 0.5
	# Surface y=0. Rain/transpiration/CO2 are above-ground tubes.
	# Infiltration goes from surface down into soil layers.
	# Nitrification/P fixation are within-layer horizontal tubes.
	var surface_y: float = 0.0
	var above: float = 0.12
	# fx_atmo = on tile surface (atmospheric), fx_soil = on cutaway face (soil)
	var test_configs: Array[Dictionary] = [
		{
			"start": Vector3(fx_atmo, surface_y + above * 2.0, fz - 0.3),
			"end": Vector3(fx_atmo, surface_y + 0.01, fz - 0.3),
			"color": COLOR_WATER,
			"magnitude": 0.8,
			"speed": 1.5,
			"label_text": "Rain",
		},
		{
			"path": _make_vertical_path(fx_soil, surface_y, l2y, fz - 0.15, 0.04),
			"color": COLOR_WATER,
			"magnitude": 0.5,
			"speed": 1.0,
			"label_text": "Infiltration",
		},
		{
			"start": Vector3(fx_atmo, surface_y + 0.01, fz),
			"end": Vector3(fx_atmo, surface_y + above * 2.0, fz),
			"color": COLOR_WATER,
			"magnitude": 0.3,
			"speed": 1.0,
			"label_text": "Transpiration",
		},
		{
			"path": _make_lateral_path(fx_soil, l1y, fz + 0.1, fz + 0.35, 0.04),
			"color": COLOR_NH4,
			"magnitude": 0.6,
			"speed": 0.8,
			"label_text": "NH4 \u2192 NO3",
		},
		{
			"path": _make_lateral_path(fx_soil, l2y, fz + 0.1, fz + 0.35, 0.04),
			"color": COLOR_PHOSPHORUS,
			"magnitude": 0.4,
			"speed": 0.5,
			"label_text": "Avail-P \u2192 Fixed-P",
		},
		{
			"start": Vector3(fx_atmo, surface_y + 0.01, fz + 0.15),
			"end": Vector3(fx_atmo, surface_y + above * 2.0, fz + 0.15),
			"color": COLOR_CARBON,
			"magnitude": 0.3,
			"speed": 1.0,
			"label_text": "CO2",
		},
	]
	for cfg in test_configs:
		var tube := FlowTube.create(cfg)
		_tubes.append(tube)
		add_child(tube)


static func _tube_key(cfg: Dictionary, idx: int) -> String:
	return cfg.get("label_text", "") + "_" + str(idx)


func _apply_gas_dissipation(tube: FlowTube, cfg: Dictionary) -> void:
	# All "up" direction tubes fade out at the top (into atmosphere)
	var ecfg: Dictionary = {}
	for etype: String in EVENT_CONFIG:
		if EVENT_CONFIG[etype].get("label", "") == cfg.get("label_text", ""):
			ecfg = EVENT_CONFIG[etype]
			break
	if ecfg.get("direction", "") == "up":
		tube.enable_gas_dissipation()


func _check_pulse_events(events: Array) -> void:
	for evt: Dictionary in events:
		var etype: String = evt.get("event_type", "")
		# Heavy rain: pulse on infiltration tubes
		if etype == "WaterInfiltrated":
			var amounts: Array = evt.get("data", {}).get("amounts_mm", [])
			var total := 0.0
			for a in amounts:
				total += float(a)
			if total > HEAVY_RAIN_MM:
				for tube in _tubes:
					if tube is FlowTube:
						var t: FlowTube = tube as FlowTube
						if t._label and t._label.text.contains("Infiltration"):
							t.pulse(PULSE_INTENSITY, PULSE_DURATION)


func clear_tubes() -> void:
	for tube in _tubes:
		tube.queue_free()
	_tubes.clear()
	_prev_configs.clear()


func _compute_layer_positions(profile_layers: Array) -> void:
	_layer_positions.clear()
	var y := 0.0
	_layer_positions.append(y)
	for layer: Dictionary in profile_layers:
		var h: float = layer.get("depth_cm", 30.0) * 0.005
		y -= h
		_layer_positions.append(y)


func _layer_midpoint_y(layer_idx: int) -> float:
	if layer_idx < 0 or layer_idx + 1 >= _layer_positions.size():
		return 0.0
	return (_layer_positions[layer_idx] + _layer_positions[layer_idx + 1]) * 0.5


static func _make_vertical_path(
	face_x: float, y_top: float, y_bot: float, face_z: float, bend_r: float
) -> Array:
	## Curve out of face at y_top, straight down, curve back in at y_bot.
	var pts: Array = []
	var steps := 5
	# Entry curve: (face_x, y_top) -> (face_x + bend_r, y_top - bend_r)
	for i in range(steps + 1):
		var t: float = float(i) / float(steps)
		var angle: float = PI * 0.5 * t
		var cx: float = face_x + sin(angle) * bend_r
		var cy: float = y_top - (1.0 - cos(angle)) * bend_r
		pts.append(Vector3(cx, cy, face_z))
	# Straight vertical section at outer X
	pts.append(Vector3(face_x + bend_r, y_bot + bend_r, face_z))
	# Exit curve: (face_x + bend_r, y_bot + bend_r) -> (face_x, y_bot)
	for i in range(steps + 1):
		var t: float = float(i) / float(steps)
		var angle: float = PI * 0.5 * t
		var cx: float = face_x + cos(angle) * bend_r
		var cy: float = y_bot + bend_r - sin(angle) * bend_r
		pts.append(Vector3(cx, cy, face_z))
	return pts


static func _make_lateral_path(
	face_x: float, y: float, z_start: float, z_end: float, bend_r: float
) -> Array:
	## Build a path: curve out of face -> straight -> curve back into face.
	## Entry: face outward (+X) then turn along +Z.
	## Exit: turn from +Z back into face (-X).
	var pts: Array = []
	var steps := 5
	# Entry curve: (face_x, z_start) -> (face_x + bend_r, z_start + bend_r)
	for i in range(steps + 1):
		var t: float = float(i) / float(steps)
		var angle: float = PI * 0.5 * t
		var cx: float = face_x + sin(angle) * bend_r
		var cz: float = z_start + (1.0 - cos(angle)) * bend_r
		pts.append(Vector3(cx, y, cz))
	# Straight section at outer X
	pts.append(Vector3(face_x + bend_r, y, z_end - bend_r))
	# Exit curve: (face_x + bend_r, z_end - bend_r) -> (face_x, z_end)
	for i in range(steps + 1):
		var t: float = float(i) / float(steps)
		var angle: float = PI * 0.5 * t
		var cx: float = face_x + cos(angle) * bend_r
		var cz: float = z_end - bend_r + sin(angle) * bend_r
		pts.append(Vector3(cx, y, cz))
	return pts


func _events_to_configs(events: Array) -> Array[Dictionary]:
	var configs: Array[Dictionary] = []
	var fx_a: float = _pillar_pos.x + 0.48
	var fx_s: float = _pillar_pos.x + 0.52
	var fz: float = _pillar_pos.z
	# Aggregate by (event_type, layer) for lateral; by event_type for vertical
	var agg: Dictionary = {}
	var agg_data: Dictionary = {}
	# Plant nutrient uptake — split NutrientStressComputed by nutrient type
	var n_uptake := 0.0
	var p_uptake := 0.0
	for evt: Dictionary in events:
		if evt.get("event_type", "") == "NutrientStressComputed":
			var d: Dictionary = evt.get("data", {})
			if d.get("nutrient", "") == "N":
				n_uptake += float(d.get("uptake_kg_ha", 0.0))
			elif d.get("nutrient", "") == "P":
				p_uptake += float(d.get("uptake_kg_ha", 0.0))
	if n_uptake > 0.01:
		(
			configs
			. append(
				{
					"start": Vector3(fx_a, 0.01, fz + 0.0),
					"end": Vector3(fx_a, 0.2, fz + 0.0),  # N uptake at z=0.0
					"color": COLOR_NO3,
					"magnitude": clampf(n_uptake / 10.0, 0.0, 1.0),
					"speed": 1.2,
					"label_text": "N uptake\n%.2f kg/ha" % n_uptake,
				}
			)
		)
	if p_uptake > 0.01:
		(
			configs
			. append(
				{
					"start": Vector3(fx_a, 0.01, fz + 0.1),
					"end": Vector3(fx_a, 0.2, fz + 0.1),  # P uptake at z=0.1
					"color": COLOR_PHOSPHORUS,
					"magnitude": clampf(p_uptake / 10.0, 0.0, 1.0),
					"speed": 1.2,
					"label_text": "P uptake\n%.3f kg/ha" % p_uptake,
				}
			)
		)
	for evt: Dictionary in events:
		var etype: String = evt.get("event_type", "")
		if etype == "NutrientStressComputed":
			continue
		if not EVENT_CONFIG.has(etype):
			continue
		var ecfg: Dictionary = EVENT_CONFIG[etype]
		var data: Dictionary = evt.get("data", {})
		var mag := _extract_magnitude(data, ecfg)
		if mag < 0.001:
			continue
		var layer_indices: Array = data.get("layer_indices", [])
		var li: int = (
			int(layer_indices[0])
			if not layer_indices.is_empty()
			else int(data.get("layer", data.get("from_layer", 0)))
		)
		# Lateral and down: per-layer. Up: aggregate across layers.
		var key: String = etype
		var dir: String = ecfg.get("direction", "")
		if dir == "lateral" or dir == "down":
			key = etype + "_L" + str(li)
		agg[key] = agg.get(key, 0.0) + mag
		if not agg_data.has(key):
			agg_data[key] = data
	# Layout zones (Z slots relative to face_z):
	# Right: water vertical (-0.4 to -0.2)
	# Center: nitrogen (0.0 to 0.15)
	# Left: carbon/phosphorus (0.25 to 0.45)
	# Atmospheric: spread above surface
	for key: String in agg:
		var etype: String = key.split("_L")[0]
		var ecfg: Dictionary = EVENT_CONFIG[etype]
		var total_mag: float = agg[key]
		var z_off: float = ecfg.get("z_slot", 0.0)
		var tube_cfg := _build_tube_config(ecfg, agg_data[key], total_mag, fx_a, fx_s, fz + z_off)
		if not tube_cfg.is_empty():
			configs.append(tube_cfg)
	# Rain connector
	var rain_total: float = agg.get("WaterInfiltrated", 0.0)
	if rain_total > RAIN_CONNECTOR_MM:
		var rain_mag: float = clampf(rain_total / 15.0, 0.1, 1.0)
		(
			configs
			. append(
				{
					"start": Vector3(fx_a, RAIN_SKY_Y, fz - 0.25),
					"end": Vector3(fx_a, 0.01, fz - 0.25),
					"color": COLOR_WATER,
					"magnitude": rain_mag,
					"speed": 2.0,
					"label_text": "Rain",
				}
			)
		)
	return configs


static func _extract_magnitude(data: Dictionary, ecfg: Dictionary) -> float:
	var mag_key: String = ecfg.get("mag_key", "")
	if mag_key == "amounts_mm_sum":
		var amounts: Array = data.get("amounts_mm", [])
		var total := 0.0
		for a in amounts:
			total += float(a)
		return total
	if mag_key.is_empty():
		return 0.0
	return float(data.get(mag_key, 0.0))


func _build_tube_config(
	ecfg: Dictionary,
	data: Dictionary,
	mag: float,
	fx_atmo: float,
	fx_soil: float,
	face_z: float,
) -> Dictionary:
	var direction: String = ecfg.get("direction", "down")
	var color: Color = ecfg.get("color", COLOR_WATER)
	var substance: String = ecfg.get("substance", "water")
	var unit: String = "mm" if substance == "water" else "kg/ha"
	# Smart precision: use enough decimals so value isn't "0.00"
	var val_str: String = "%.2f" % mag
	if mag > 0.0 and mag < 0.005:
		val_str = "%.3f" % mag
	# Skip tube if value too small to display meaningfully
	# Water: < 0.01 mm. Other: < 0.01 kg/ha
	var min_display: float = 0.01
	if mag < min_display:
		return {}
	var label: String = "%s\n%s %s" % [ecfg.get("label", ""), val_str, unit]
	# Normalize to 0-1. Water in mm, everything else in kg/ha.
	# Single scale per unit so cross-substance comparison is meaningful:
	# 0.004 kg/ha P should look tiny next to 7 kg/ha decomposition.
	var norm_mag: float = 0.0
	if substance == "water":
		norm_mag = clampf(mag / 5.0, 0.0, 1.0)
	else:
		# All kg/ha substances on the same scale: 0-10 kg/ha = 0-1
		# P at 0.004 → 0.0004, Nitrif at 3 → 0.3, Decomp at 50 → capped 1.0
		norm_mag = clampf(mag / 10.0, 0.0, 1.0)

	# WaterInfiltrated uses "layer_indices" array; others use "layer" or "from_layer"
	var layer_indices: Array = data.get("layer_indices", [])
	var layer_idx: int = (
		int(layer_indices[0])
		if not layer_indices.is_empty()
		else int(data.get("layer", data.get("from_layer", 0)))
	)
	var tube_z: float = face_z
	var start := Vector3.ZERO
	var end := Vector3.ZERO
	# Fixed moderate speed; magnitude modulates particle count instead
	var speed: float = 1.2

	match direction:
		"down":
			var y_top: float = 0.0 if layer_idx == 0 else _layer_midpoint_y(layer_idx)
			var y_bot := _layer_midpoint_y(mini(layer_idx + 1, _layer_positions.size() - 2))
			if absf(y_top - y_bot) < 0.001:
				y_bot = y_top - 0.1
			var path := _make_vertical_path(fx_soil, y_top, y_bot, tube_z, 0.04)
			speed = absf(speed)
			return {
				"path": path,
				"color": color,
				"magnitude": norm_mag,
				"speed": speed,
				"label_text": label,
			}
		"up":
			start = Vector3(fx_atmo, 0.01, tube_z)
			end = Vector3(fx_atmo, 0.2, tube_z)
			speed = absf(speed)
		"lateral":
			# Stack within layer using y_frac (0=top, 1=bottom of layer)
			var y_frac: float = ecfg.get("y_frac", 0.5)
			var y_top_l: float = (
				_layer_positions[layer_idx] if layer_idx < _layer_positions.size() else 0.0
			)
			var y_bot_l: float = (
				_layer_positions[layer_idx + 1]
				if layer_idx + 1 < _layer_positions.size()
				else y_top_l - 0.1
			)
			var y_pos: float = lerpf(y_top_l, y_bot_l, y_frac)
			var path := _make_lateral_path(fx_soil, y_pos, tube_z, tube_z + 0.15, 0.03)
			speed = absf(speed)
			return {
				"path": path,
				"color": color,
				"magnitude": norm_mag,
				"speed": speed,
				"label_text": label,
			}

	return {
		"start": start,
		"end": end,
		"color": color,
		"magnitude": norm_mag,
		"speed": speed,
		"label_text": label,
	}
