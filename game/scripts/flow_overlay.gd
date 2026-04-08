class_name FlowOverlay
extends Node3D
## Flow tube network overlay for the soil cutaway.
## Maps simulation events to glass-tube visualizations with animated particles.
## Sits as a child of the cutaway container; updated on each step.

const MAX_TUBES := 20

## Substance colors per art guide
const COLOR_WATER := Color(0.376, 0.647, 0.980, 0.8)
const COLOR_NITROGEN := Color(0.290, 0.871, 0.502, 0.8)
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
		"color": COLOR_NITROGEN,
		"substance": "nitrogen",
		"direction": "lateral",
		"mag_key": "amount_kg_ha",
		"label": "Nitrification",
	},
	"MineralizationOccurred":
	{
		"color": COLOR_NITROGEN,
		"substance": "nitrogen",
		"direction": "lateral",
		"mag_key": "amount_kg_ha",
		"label": "Mineralization",
	},
	"DenitrificationOccurred":
	{
		"color": COLOR_NITROGEN,
		"substance": "nitrogen",
		"direction": "up",
		"mag_key": "amount_kg_ha",
		"label": "Denitrification",
	},
	"VolatilizationOccurred":
	{
		"color": COLOR_NITROGEN,
		"substance": "nitrogen",
		"direction": "up",
		"mag_key": "amount_kg_ha",
		"label": "Volatilization",
	},
	"NutrientLeached":
	{
		"color": COLOR_NITROGEN,
		"substance": "nitrogen",
		"direction": "down",
		"mag_key": "amount_kg_ha",
		"label": "Leaching",
	},
	"PhosphorusFixationOccurred":
	{
		"color": COLOR_PHOSPHORUS,
		"substance": "phosphorus",
		"direction": "lateral",
		"mag_key": "amount_fixed_kg_ha",
		"label": "P Fixation",
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
	# +X face of the cutaway box (CUTAWAY_WIDTH/2 + offset from pillar)
	var fx: float = pillar_pos.x + 0.52
	var fz: float = pillar_pos.z
	# Spread tubes along the Z axis on the face
	# Vertical tubes in a column at the face, spread along Z
	# Lateral tubes run along Z at the face, at layer midpoints
	var l1y: float = (_layer_positions[0] + _layer_positions[1]) * 0.5
	var l2y: float = (_layer_positions[1] + _layer_positions[2]) * 0.5
	var l3y: float = (_layer_positions[2] + _layer_positions[3]) * 0.5
	var test_configs: Array[Dictionary] = [
		{
			"start": Vector3(fx, 0.06, fz - 0.3),
			"end": Vector3(fx, l1y, fz - 0.3),
			"color": COLOR_WATER,
			"magnitude": 0.8,
			"speed": 1.5,
			"label_text": "Rain",
		},
		{
			"start": Vector3(fx, l1y, fz - 0.15),
			"end": Vector3(fx, l2y, fz - 0.15),
			"color": COLOR_WATER,
			"magnitude": 0.5,
			"speed": 1.0,
			"label_text": "Infiltration",
		},
		{
			"start": Vector3(fx, l2y, fz),
			"end": Vector3(fx, 0.04, fz),
			"color": COLOR_WATER,
			"magnitude": 0.3,
			"speed": 1.0,
			"label_text": "Transpiration",
		},
		{
			"start": Vector3(fx, l1y, fz + 0.1),
			"end": Vector3(fx, l1y, fz + 0.35),
			"color": COLOR_NITROGEN,
			"magnitude": 0.6,
			"speed": 0.8,
			"label_text": "Nitrification",
		},
		{
			"start": Vector3(fx, l2y, fz + 0.1),
			"end": Vector3(fx, l2y, fz + 0.35),
			"color": COLOR_PHOSPHORUS,
			"magnitude": 0.4,
			"speed": 0.5,
			"label_text": "P Fixation",
		},
		{
			"start": Vector3(fx, l3y, fz + 0.15),
			"end": Vector3(fx, 0.04, fz + 0.15),
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


func _events_to_configs(events: Array) -> Array[Dictionary]:
	var configs: Array[Dictionary] = []
	# +X face of cutaway box (CUTAWAY_WIDTH/2 + small offset)
	var face_x: float = _pillar_pos.x + 0.52
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
		var tube_cfg := _build_tube_config(ecfg, data, mag, face_x, face_z)
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
	face_x: float,
	face_z: float,
) -> Dictionary:
	var direction: String = ecfg.get("direction", "down")
	var color: Color = ecfg.get("color", COLOR_WATER)
	var label: String = ecfg.get("label", "")
	# Normalize magnitude: water in mm (0-20), nutrients in kg/ha (0-5)
	var norm_mag: float = 0.5
	match ecfg.get("substance", "water"):
		"water":
			norm_mag = clampf(mag / 10.0, 0.05, 1.0)
		"nitrogen", "phosphorus":
			norm_mag = clampf(mag / 2.0, 0.05, 1.0)
		"carbon":
			norm_mag = clampf(mag / 5.0, 0.05, 1.0)

	var layer_idx: int = int(data.get("layer", data.get("from_layer", 0)))
	var start := Vector3.ZERO
	var end := Vector3.ZERO
	var speed: float = norm_mag * 2.0

	match direction:
		"down":
			var y_top := _layer_midpoint_y(layer_idx)
			var y_bot := _layer_midpoint_y(mini(layer_idx + 1, _layer_positions.size() - 2))
			if absf(y_top - y_bot) < 0.001:
				y_bot = y_top - 0.1
			start = Vector3(face_x, y_top, face_z)
			end = Vector3(face_x, y_bot, face_z)
			speed = absf(speed)
		"up":
			var y_mid := _layer_midpoint_y(layer_idx)
			start = Vector3(face_x, y_mid, face_z)
			end = Vector3(face_x, y_mid + 0.1, face_z)
			speed = -absf(speed)
		"lateral":
			var y_mid := _layer_midpoint_y(layer_idx)
			start = Vector3(face_x, y_mid, face_z + 0.05)
			end = Vector3(face_x, y_mid, face_z + 0.3)
			speed = absf(speed)

	return {
		"start": start,
		"end": end,
		"color": color,
		"magnitude": norm_mag,
		"speed": speed,
		"label_text": label,
	}
