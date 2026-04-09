class_name StressIcons
extends Node3D
## Floating warning icons above tiles for weather damage events.
## Uses SVG icon sprites. Label shown on hover or close camera zoom.

const ICON_Y := 0.5
const ICON_SIZE := Vector2(0.10, 0.10)
const LABEL_ZOOM_THRESHOLD := 2.5

## Event types that trigger stress icons.
const STRESS_EVENTS := {
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

var _icons: Dictionary = {}
var _labels: Array[Label3D] = []


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
			for evt: Dictionary in events:
				var etype: String = evt.get("event_type", "")
				if STRESS_EVENTS.has(etype):
					active_stresses[soil + "_" + etype] = {"soil": soil, "event": etype}
	var tile_stresses: Dictionary = {}
	for key: String in active_stresses:
		var info: Dictionary = active_stresses[key]
		for i in range(tile_data.size()):
			if tile_data[i].get("soil_type", "") == info["soil"]:
				if not tile_stresses.has(i):
					tile_stresses[i] = []
				tile_stresses[i].append(info["event"])
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
	# Create new
	for tile_idx: int in tile_stresses:
		var key: String = str(tile_idx)
		if _icons.has(key):
			continue
		var pos: Vector3 = tile_meshes[tile_idx].position
		var node := _create_icons(pos, tile_stresses[tile_idx])
		add_child(node)
		_icons[key] = node
		_animate_appear(node)
		_collect_labels(node)


func clear_icons() -> void:
	for key: String in _icons:
		_icons[key].queue_free()
	_icons.clear()
	_labels.clear()


func _collect_labels(node: Node3D) -> void:
	for child in node.get_children():
		if child is Label3D and child.has_meta("stress_label"):
			_labels.append(child)


func _create_icons(pos: Vector3, etypes: Array) -> Node3D:
	var container := Node3D.new()
	container.position = Vector3(pos.x, pos.y, pos.z)
	var x_offset := 0.0
	for etype: String in etypes:
		if not STRESS_EVENTS.has(etype):
			continue
		var cfg: Dictionary = STRESS_EVENTS[etype]
		# Sprite icon
		var sprite := Sprite3D.new()
		sprite.texture = load(cfg["texture"])
		sprite.pixel_size = ICON_SIZE.x / maxf(sprite.texture.get_width(), 1.0)
		sprite.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		sprite.no_depth_test = true
		sprite.render_priority = 14
		sprite.position = Vector3(x_offset, ICON_Y, 0)
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
		lbl.position = Vector3(x_offset, ICON_Y - 0.08, 0)
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
		area.position = Vector3(x_offset, ICON_Y, 0)
		area.input_ray_pickable = true
		var lbl_ref := lbl
		area.mouse_entered.connect(
			func() -> void:
				lbl_ref.visible = true
				lbl_ref.set_meta("hovered", true)
		)
		area.mouse_exited.connect(func() -> void: lbl_ref.remove_meta("hovered"))
		container.add_child(area)
		x_offset += 0.20
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
