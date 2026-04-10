class_name StressIcons
extends Node3D
## Floating warning icons above tiles for crop stress conditions.
## Uses SVG icon sprites. Label shown on hover or close camera zoom.
## Detects both event-based stress (frost/heat/waterlogging) and
## threshold-based stress (drought, N/P deficiency).

const ICON_Y := 0.5
const ICON_SIZE := Vector2(0.08, 0.08)
const ICON_SPACING := 0.14
const LABEL_ZOOM_THRESHOLD := 2.5
const STRESS_THRESHOLD := 0.5

## Event-based stress: icon shown when event is present in day's events.
const EVENT_STRESS := {
	"FrostDamageApplied":
	{
		"texture": "res://assets/icons/icon_frost.svg",
		"label": "Frost damage",
		"color": UiTheme.SUBSTANCE_FROST,
	},
	"HeatDamageApplied":
	{
		"texture": "res://assets/icons/icon_heat.svg",
		"label": "Heat stress",
		"color": UiTheme.SUBSTANCE_HEAT,
	},
	"WaterloggingDetected":
	{
		"texture": "res://assets/icons/icon_waterlogging.svg",
		"label": "Waterlogged",
		"color": UiTheme.SUBSTANCE_WATER,
	},
}

## Threshold-based stress: icon shown when stress factor < STRESS_THRESHOLD.
const THRESHOLD_STRESS := {
	"drought":
	{
		"texture": "res://assets/icons/icon_drought.svg",
		"label": "Drought",
		"color": Color(0.75, 0.55, 0.30, 0.8),
	},
	"n_deficiency":
	{
		"texture": "res://assets/icons/icon_n_deficiency.svg",
		"label": "N deficiency",
		"color": UiTheme.SUBSTANCE_NO3,
	},
	"p_deficiency":
	{
		"texture": "res://assets/icons/icon_p_deficiency.svg",
		"label": "P deficiency",
		"color": UiTheme.SUBSTANCE_PHOSPHORUS,
	},
}

## Combined lookup for icon creation.
var _all_stress: Dictionary = {}

var _icons: Dictionary = {}
var _labels: Array[Label3D] = []


func _ready() -> void:
	_all_stress.merge(EVENT_STRESS)
	_all_stress.merge(THRESHOLD_STRESS)


func _process(_delta: float) -> void:
	var cam := get_viewport().get_camera_3d()
	if not cam:
		return
	var zoom: float = cam.size if cam is Camera3D else 10.0
	var close: bool = zoom < LABEL_ZOOM_THRESHOLD
	for lbl: Label3D in _labels:
		if is_instance_valid(lbl) and not lbl.has_meta("hovered"):
			lbl.visible = close


func update_from_patches(
	patches: Dictionary, tile_data: Array, tile_meshes: Array, soil_types: Array
) -> void:
	var active_stresses: Dictionary = {}
	for field_key: String in patches:
		var patch_list: Array = patches[field_key]
		for pi in range(patch_list.size()):
			var patch: Dictionary = patch_list[pi]
			var events: Array = patch.get("events", [])
			var soil: String = soil_types[pi] if pi < soil_types.size() else ""
			# Event-based stress
			for evt: Dictionary in events:
				var etype: String = evt.get("event_type", "")
				if EVENT_STRESS.has(etype):
					active_stresses[soil + "_" + etype] = {"soil": soil, "stress_key": etype}
				# Threshold-based: water stress
				if etype == "WaterStressComputed":
					var stress: float = float(evt.get("data", {}).get("stress", 1.0))
					if stress < STRESS_THRESHOLD:
						active_stresses[soil + "_drought"] = {"soil": soil, "stress_key": "drought"}
				# Threshold-based: nutrient stress
				if etype == "NutrientStressComputed":
					var data: Dictionary = evt.get("data", {})
					var nutrient: String = str(data.get("nutrient", ""))
					var stress: float = float(data.get("stress", 1.0))
					if stress < STRESS_THRESHOLD:
						if nutrient == "N":
							active_stresses[soil + "_n_deficiency"] = {
								"soil": soil, "stress_key": "n_deficiency"
							}
						elif nutrient == "P":
							active_stresses[soil + "_p_deficiency"] = {
								"soil": soil, "stress_key": "p_deficiency"
							}
				# Redox: anaerobic stress when Eh < -100 mV
				if etype == "RedoxChanged":
					var eh: float = float(evt.get("data", {}).get("eh_mv", 400.0))
					if eh < -100.0:
						active_stresses[soil + "_anaerobic"] = {
							"soil": soil, "stress_key": "anaerobic"
						}
	# Map stresses to tile indices
	var tile_stresses: Dictionary = {}
	for key: String in active_stresses:
		var info: Dictionary = active_stresses[key]
		for i in range(tile_data.size()):
			if tile_data[i].get("soil_type", "") == info["soil"]:
				if not tile_stresses.has(i):
					tile_stresses[i] = []
				var sk: String = info["stress_key"]
				if sk not in tile_stresses[i]:
					tile_stresses[i].append(sk)
	# Remove stale icons
	var to_remove: Array = []
	for icon_key: String in _icons:
		if not tile_stresses.has(int(icon_key)):
			to_remove.append(icon_key)
	for key: String in to_remove:
		_animate_remove(_icons[key])
		_icons.erase(key)
	_labels.clear()
	for key: String in _icons:
		_collect_labels(_icons[key])
	# Create/update icons
	for tile_idx: int in tile_stresses:
		var key: String = str(tile_idx)
		var stress_keys: Array = tile_stresses[tile_idx]
		if _icons.has(key):
			# Update if stress set changed
			var existing: Node3D = _icons[key]
			var old_keys: Array = existing.get_meta("stress_keys", [])
			if _arrays_equal(old_keys, stress_keys):
				_collect_labels(existing)
				continue
			existing.queue_free()
			_icons.erase(key)
		var pos: Vector3 = tile_meshes[tile_idx].position
		var node := _create_icons(pos, stress_keys)
		node.set_meta("stress_keys", stress_keys)
		add_child(node)
		_icons[key] = node
		_animate_appear(node)
		_collect_labels(node)


func clear_icons() -> void:
	for key: String in _icons:
		_icons[key].queue_free()
	_icons.clear()
	_labels.clear()


static func _arrays_equal(a: Array, b: Array) -> bool:
	## Order-insensitive comparison (stress keys may arrive in different order).
	if a.size() != b.size():
		return false
	var sa := a.duplicate()
	sa.sort()
	var sb := b.duplicate()
	sb.sort()
	return sa == sb


func _collect_labels(node: Node3D) -> void:
	for child in node.get_children():
		if child is Label3D and child.has_meta("stress_label"):
			_labels.append(child)


func _create_icons(pos: Vector3, stress_keys: Array) -> Node3D:
	var container := Node3D.new()
	container.position = Vector3(pos.x, pos.y, pos.z)
	# Center the icon row
	var total_width: float = maxf(0.0, float(stress_keys.size() - 1) * ICON_SPACING)
	var x_start: float = -total_width * 0.5
	for si in range(stress_keys.size()):
		var skey: String = stress_keys[si]
		if not _all_stress.has(skey):
			continue
		var cfg: Dictionary = _all_stress[skey]
		var x_pos: float = x_start + float(si) * ICON_SPACING
		# Sprite icon
		var tex_path: String = cfg["texture"]
		if not ResourceLoader.exists(tex_path):
			continue
		var sprite := Sprite3D.new()
		sprite.texture = load(tex_path)
		sprite.pixel_size = ICON_SIZE.x / maxf(sprite.texture.get_width(), 1.0)
		sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		sprite.no_depth_test = true
		sprite.render_priority = 14
		sprite.position = Vector3(x_pos, ICON_Y, 0)
		container.add_child(sprite)
		# Label below
		var lbl := Label3D.new()
		lbl.text = cfg["label"]
		lbl.font_size = 22
		lbl.pixel_size = 0.002
		lbl.modulate = cfg["color"]
		lbl.outline_size = 6
		lbl.outline_modulate = Color(0, 0, 0, 0.7)
		lbl.no_depth_test = true
		lbl.render_priority = 14
		lbl.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		lbl.position = Vector3(x_pos, ICON_Y - 0.08, 0)
		lbl.visible = false
		lbl.set_meta("stress_label", true)
		container.add_child(lbl)
		# Hover area
		var area := Area3D.new()
		var coll := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = Vector3(0.12, 0.15, 0.12)
		coll.shape = shape
		area.add_child(coll)
		area.position = Vector3(x_pos, ICON_Y, 0)
		area.input_ray_pickable = true
		var lbl_ref := lbl
		area.mouse_entered.connect(
			func() -> void:
				lbl_ref.visible = true
				lbl_ref.set_meta("hovered", true)
		)
		# Remove hovered meta; _process will hide on next frame if not zoomed in.
		area.mouse_exited.connect(func() -> void: lbl_ref.remove_meta("hovered"))
		container.add_child(area)
	return container


func _animate_appear(node: Node3D) -> void:
	node.scale = Vector3(0.01, 0.01, 0.01)
	var tw := create_tween()
	tw.set_ease(Tween.EASE_OUT)
	tw.set_trans(Tween.TRANS_BACK)
	tw.tween_property(node, "scale", Vector3.ONE, 0.5)


func _animate_remove(node: Node3D) -> void:
	var tw := create_tween()
	tw.set_ease(Tween.EASE_IN)
	tw.set_trans(Tween.TRANS_BACK)
	tw.tween_property(node, "scale", Vector3(0.01, 0.01, 0.01), 0.3)
	tw.tween_callback(node.queue_free)
