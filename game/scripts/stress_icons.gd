class_name StressIcons
extends Node3D
## Floating warning signs above tiles for weather damage events.
## Yellow triangle with colored icon. Label shown on hover or close zoom.

const ICON_Y := 0.55
const SIGN_SIZE := 0.07
const POLE_HEIGHT := 0.25
const POLE_RADIUS := 0.003
const LABEL_ZOOM_THRESHOLD := 5.0

## Event types that trigger stress icons.
const STRESS_EVENTS := {
	"FrostDamageApplied":
	{
		"icon": "❄",
		"label": "Frost damage",
		"color": UiTheme.SUBSTANCE_FROST,
	},
	"HeatDamageApplied":
	{
		"icon": "☀",
		"label": "Heat stress",
		"color": UiTheme.SUBSTANCE_HEAT,
	},
	"WaterloggingDetected":
	{
		"icon": "💧",
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
		var soil: String = info["soil"]
		var etype: String = info["event"]
		for i in range(tile_data.size()):
			if tile_data[i].get("soil_type", "") == soil:
				if not tile_stresses.has(i):
					tile_stresses[i] = []
				tile_stresses[i].append(etype)
	# Remove stale icons with shrink animation
	var to_remove: Array = []
	for icon_key: String in _icons:
		if not tile_stresses.has(int(icon_key)):
			to_remove.append(icon_key)
	for key: String in to_remove:
		var node: Node3D = _icons[key]
		_animate_remove(node)
		_icons.erase(key)
	_labels.clear()
	# Collect still-valid labels
	for key: String in _icons:
		_collect_labels(_icons[key])
	# Create new icons
	for tile_idx: int in tile_stresses:
		var etypes: Array = tile_stresses[tile_idx]
		var key: String = str(tile_idx)
		if _icons.has(key):
			continue
		var pos: Vector3 = tile_meshes[tile_idx].position
		var sign_node := _create_sign(pos, etypes)
		add_child(sign_node)
		_icons[key] = sign_node
		_animate_appear(sign_node)
		_collect_labels(sign_node)


func clear_icons() -> void:
	for key: String in _icons:
		_icons[key].queue_free()
	_icons.clear()
	_labels.clear()


func _collect_labels(node: Node3D) -> void:
	for child in node.get_children():
		if child is Node3D:
			for sub in child.get_children():
				if sub is Label3D and sub.has_meta("stress_label"):
					_labels.append(sub)


func _create_sign(pos: Vector3, etypes: Array) -> Node3D:
	var container := Node3D.new()
	container.position = Vector3(pos.x, pos.y, pos.z)
	var x_offset := 0.0
	for etype: String in etypes:
		if not STRESS_EVENTS.has(etype):
			continue
		var cfg: Dictionary = STRESS_EVENTS[etype]
		var sign_root := Node3D.new()
		sign_root.position = Vector3(x_offset, 0, 0)
		container.add_child(sign_root)
		_build_pole(sign_root)
		_build_triangle(sign_root)
		_build_icon(sign_root, cfg)
		_build_label(sign_root, cfg)
		_build_hover_area(sign_root)
		x_offset += 0.18
	return container


func _build_pole(parent: Node3D) -> void:
	var pole_mesh := CylinderMesh.new()
	pole_mesh.height = POLE_HEIGHT
	pole_mesh.top_radius = POLE_RADIUS
	pole_mesh.bottom_radius = POLE_RADIUS
	pole_mesh.radial_segments = 6
	var pole_mat := StandardMaterial3D.new()
	pole_mat.albedo_color = Color(0.5, 0.5, 0.5)
	pole_mat.metallic = 0.6
	pole_mat.roughness = 0.4
	var pole_inst := MeshInstance3D.new()
	pole_inst.mesh = pole_mesh
	pole_inst.material_override = pole_mat
	pole_inst.position = Vector3(0, ICON_Y - POLE_HEIGHT * 0.5, 0)
	parent.add_child(pole_inst)


func _build_triangle(parent: Node3D) -> void:
	# Yellow warning triangle built with SurfaceTool (billboard via Label3D backing)
	# Using a simple quad with triangle UV would be complex — use two Label3Ds instead:
	# a yellow triangle character as background
	var bg := Label3D.new()
	bg.text = "⚠"
	bg.font_size = 72
	bg.pixel_size = 0.0025
	bg.modulate = Color(1.0, 0.85, 0.0)
	bg.outline_size = 12
	bg.outline_modulate = Color(0.15, 0.15, 0.15)
	bg.no_depth_test = true
	bg.render_priority = 13
	bg.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	bg.position = Vector3(0, ICON_Y + 0.01, 0)
	parent.add_child(bg)


func _build_icon(parent: Node3D, cfg: Dictionary) -> void:
	var icon_label := Label3D.new()
	icon_label.text = cfg["icon"]
	icon_label.font_size = 28
	icon_label.pixel_size = 0.0018
	icon_label.modulate = cfg["color"]
	icon_label.no_depth_test = true
	icon_label.render_priority = 15
	icon_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	icon_label.position = Vector3(0, ICON_Y - 0.005, -0.001)
	parent.add_child(icon_label)


func _build_label(parent: Node3D, cfg: Dictionary) -> void:
	var text_label := Label3D.new()
	text_label.text = cfg["label"]
	text_label.font_size = 22
	text_label.pixel_size = 0.002
	text_label.modulate = cfg["color"]
	text_label.outline_size = 6
	text_label.outline_modulate = Color(0, 0, 0, 0.7)
	text_label.no_depth_test = true
	text_label.render_priority = 14
	text_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	text_label.position = Vector3(0, ICON_Y - 0.05, 0)
	text_label.visible = false
	text_label.set_meta("stress_label", true)
	parent.add_child(text_label)


func _build_hover_area(parent: Node3D) -> void:
	var area := Area3D.new()
	var coll := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = Vector3(0.12, 0.15, 0.12)
	coll.shape = shape
	area.add_child(coll)
	area.position = Vector3(0, ICON_Y, 0)
	area.input_ray_pickable = true
	# Find the label in siblings
	var lbl: Label3D = null
	for child in parent.get_children():
		if child is Label3D and child.has_meta("stress_label"):
			lbl = child
			break
	if lbl:
		var lbl_ref := lbl
		area.mouse_entered.connect(
			func() -> void:
				lbl_ref.visible = true
				lbl_ref.set_meta("hovered", true)
		)
		area.mouse_exited.connect(func() -> void: lbl_ref.remove_meta("hovered"))
	parent.add_child(area)


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
