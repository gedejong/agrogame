class_name FlowOverlay
extends Node3D
## Flow tube network overlay for the soil cutaway.
## Maps simulation events to glass-tube visualizations with animated particles.
## Sits as a child of the cutaway container; updated on each step.

const MAX_TUBES := 20

## Substance colors — NH4 and NO3 distinct for visible transformations
const COLOR_WATER := Color(0.376, 0.647, 0.980, 0.8)
const COLOR_NO3 := Color(0.290, 0.871, 0.502, 0.8)  # bright green — mobile nitrate
const COLOR_NH4 := Color(0.2, 0.75, 0.75, 0.8)  # teal/cyan — ammonium (held by clay)
const COLOR_ORGANIC_N := Color(0.45, 0.65, 0.35, 0.8)  # olive — locked in organic matter
const COLOR_PHOSPHORUS := Color(0.655, 0.545, 0.980, 0.8)  # #A78BFA
const COLOR_CARBON := Color(0.984, 0.749, 0.141, 0.8)

## Event type → tube config mapping
const EVENT_CONFIG := {
	"WaterInfiltrated":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "down",
		"mag_key": "amounts_mm_sum",
		"label": "Infiltration",
	},
	"WaterDrained":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "down",
		"mag_key": "amount_mm",
		"label": "Percolation",
	},
	"EvaporationTaken":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "up",
		"mag_key": "amount_mm",
		"label": "Evaporation",
	},
	"TranspirationByLayer":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "up",
		"mag_key": "total_mm",
		"label": "Transpiration",
	},
	"RunoffGenerated":
	{
		"color": COLOR_WATER,
		"substance": "water",
		"direction": "lateral",
		"mag_key": "amount_mm",
		"label": "Runoff",
	},
	"NitrificationOccurred":
	{
		"color": COLOR_NH4,
		"substance": "nitrogen",
		"direction": "lateral",
		"mag_key": "amount_kg_ha",
		"label": "NH4 \u2192 NO3",
	},
	"MineralizationOccurred":
	{
		"color": COLOR_ORGANIC_N,
		"substance": "nitrogen",
		"direction": "lateral",
		"mag_key": "amount_kg_ha",
		"label": "Org-N \u2192 NH4",
	},
	"DenitrificationOccurred":
	{
		"color": COLOR_NO3,
		"substance": "nitrogen",
		"direction": "up",
		"mag_key": "amount_kg_ha",
		"label": "Denitrification",
	},
	"VolatilizationOccurred":
	{
		"color": COLOR_NH4,
		"substance": "nitrogen",
		"direction": "up",
		"mag_key": "amount_kg_ha",
		"label": "NH3 loss",
	},
	"NutrientLeached":
	{
		"color": COLOR_NO3,
		"substance": "nitrogen",
		"direction": "down",
		"mag_key": "amount_kg_ha",
		"label": "NO3 leaching",
	},
	"PhosphorusFixationOccurred":
	{
		"color": COLOR_PHOSPHORUS,
		"substance": "phosphorus",
		"direction": "lateral",
		"mag_key": "amount_fixed_kg_ha",
		"label": "Avail-P \u2192 Fixed-P",
	},
	"SOMDecomposed":
	{
		"color": COLOR_CARBON,
		"substance": "carbon",
		"direction": "lateral",
		"mag_key": "decomposed_c_kg_ha",
		"label": "Decomposition",
	},
	"CO2Respired":
	{
		"color": COLOR_CARBON,
		"substance": "carbon",
		"direction": "up",
		"mag_key": "co2_c_kg_ha",
		"label": "CO2 Respiration",
	},
}

var _tubes: Array[Node3D] = []
var _layer_positions: Array[float] = []
var _pillar_pos := Vector3.ZERO


func update_from_events(events: Array, profile_layers: Array, pillar_pos: Vector3) -> void:
	## Rebuild tube network from simulation events.
	clear_tubes()
	_compute_layer_positions(profile_layers)
	_pillar_pos = pillar_pos
	var tube_configs := _events_to_configs(events)
	# Cull to MAX_TUBES by magnitude
	tube_configs.sort_custom(
		func(a: Dictionary, b: Dictionary) -> bool:
			return a.get("magnitude", 0.0) > b.get("magnitude", 0.0)
	)
	var count := mini(tube_configs.size(), MAX_TUBES)
	for i in range(count):
		var tube := FlowTube.create(tube_configs[i])
		_tubes.append(tube)
		add_child(tube)


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
	var l3y: float = (_layer_positions[2] + _layer_positions[3]) * 0.5
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


func clear_tubes() -> void:
	for tube in _tubes:
		tube.queue_free()
	_tubes.clear()


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
	var face_x_atmo: float = _pillar_pos.x + 0.48
	var face_x_soil: float = _pillar_pos.x + 0.52
	var face_z: float = _pillar_pos.z
	for evt: Dictionary in events:
		var etype: String = evt.get("event_type", "")
		if not EVENT_CONFIG.has(etype):
			continue
		var ecfg: Dictionary = EVENT_CONFIG[etype]
		var data: Dictionary = evt.get("data", {})
		var mag := _extract_magnitude(data, ecfg)
		if mag < 0.001:
			continue
		var tube_cfg := _build_tube_config(ecfg, data, mag, face_x_atmo, face_x_soil, face_z)
		if not tube_cfg.is_empty():
			configs.append(tube_cfg)
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
	var label: String = ecfg.get("label", "")
	var norm_mag: float = 0.5
	match ecfg.get("substance", "water"):
		"water":
			norm_mag = clampf(mag / 10.0, 0.05, 1.0)
		"nitrogen", "phosphorus":
			norm_mag = clampf(mag / 2.0, 0.05, 1.0)
		"carbon":
			norm_mag = clampf(mag / 5.0, 0.05, 1.0)

	# WaterInfiltrated uses "layer_indices" array; others use "layer" or "from_layer"
	var layer_indices: Array = data.get("layer_indices", [])
	var layer_idx: int = (
		int(layer_indices[0])
		if not layer_indices.is_empty()
		else int(data.get("layer", data.get("from_layer", 0)))
	)
	var start := Vector3.ZERO
	var end := Vector3.ZERO
	var speed: float = norm_mag * 2.0

	match direction:
		"down":
			# Infiltration/percolation: curved out, down, curved back in
			var y_top: float = 0.0 if layer_idx == 0 else _layer_midpoint_y(layer_idx)
			var y_bot := _layer_midpoint_y(mini(layer_idx + 1, _layer_positions.size() - 2))
			if absf(y_top - y_bot) < 0.001:
				y_bot = y_top - 0.1
			var path := _make_vertical_path(fx_soil, y_top, y_bot, face_z, 0.04)
			speed = absf(speed)
			return {
				"path": path,
				"color": color,
				"magnitude": norm_mag,
				"speed": speed,
				"label_text": label,
			}
		"up":
			# Atmospheric: on tile surface, upward
			start = Vector3(fx_atmo, 0.01, face_z)
			end = Vector3(fx_atmo, 0.2, face_z)
			speed = absf(speed)
		"lateral":
			# Within-layer: curved path — out of face, straight, back in
			var y_mid := _layer_midpoint_y(layer_idx)
			var path := _make_lateral_path(fx_soil, y_mid, face_z + 0.05, face_z + 0.3, 0.04)
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
