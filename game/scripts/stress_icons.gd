class_name StressIcons
extends Node3D
## Floating warning signs above tiles for weather damage events.
## American-style diamond warning sign with icon. Label shown on
## hover or when camera is zoomed in close.

const ICON_Y := 0.55
const SIGN_SIZE := 0.08
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
	# Show/hide labels based on camera zoom distance
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
	## Scan patch events for stress, show/hide icons above affected tiles.
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
					active_stresses[soil + "_" + etype] = {
						"soil": soil,
						"event": etype,
					}
	# Find tile positions for active stresses
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
	# Remove icons for tiles no longer stressed
	var to_remove: Array = []
	for icon_key: String in _icons:
		if not tile_stresses.has(int(icon_key)):
			to_remove.append(icon_key)
	for key: String in to_remove:
		var node: Node3D = _icons[key]
		node.queue_free()
		_icons.erase(key)
	# Rebuild labels list
	_labels.clear()
	# Create/update icons for stressed tiles
	for tile_idx: int in tile_stresses:
		var etypes: Array = tile_stresses[tile_idx]
		var key: String = str(tile_idx)
		if _icons.has(key):
			_rebuild_sign(_icons[key], etypes)
		else:
			var pos: Vector3 = tile_meshes[tile_idx].position
			var sign_node := _create_sign(pos, etypes)
			add_child(sign_node)
			_icons[key] = sign_node


func clear_icons() -> void:
	for key: String in _icons:
		_icons[key].queue_free()
	_icons.clear()
	_labels.clear()


func _create_sign(pos: Vector3, etypes: Array) -> Node3D:
	var container := Node3D.new()
	container.position = Vector3(pos.x, pos.y, pos.z)
	_build_sign_content(container, etypes)
	return container


func _rebuild_sign(container: Node3D, etypes: Array) -> void:
	for child in container.get_children():
		child.queue_free()
	_build_sign_content(container, etypes)


func _build_sign_content(container: Node3D, etypes: Array) -> void:
	var x_offset := 0.0
	for etype: String in etypes:
		if not STRESS_EVENTS.has(etype):
			continue
		var cfg: Dictionary = STRESS_EVENTS[etype]
		var sign_root := Node3D.new()
		sign_root.position = Vector3(x_offset, 0, 0)
		container.add_child(sign_root)
		# Pole
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
		sign_root.add_child(pole_inst)
		# Diamond sign background (rotated square quad)
		var quad := QuadMesh.new()
		quad.size = Vector2(SIGN_SIZE, SIGN_SIZE)
		var sign_mat := StandardMaterial3D.new()
		sign_mat.albedo_color = Color(1.0, 0.85, 0.0)
		sign_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		sign_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		sign_mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		var sign_inst := MeshInstance3D.new()
		sign_inst.mesh = quad
		sign_inst.material_override = sign_mat
		sign_inst.position = Vector3(0, ICON_Y + 0.01, 0)
		sign_inst.rotation.z = PI * 0.25
		sign_root.add_child(sign_inst)
		# Black border (slightly larger diamond behind)
		var border_quad := QuadMesh.new()
		border_quad.size = Vector2(SIGN_SIZE * 1.12, SIGN_SIZE * 1.12)
		var border_mat := StandardMaterial3D.new()
		border_mat.albedo_color = Color(0.1, 0.1, 0.1)
		border_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		border_mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		border_mat.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
		var border_inst := MeshInstance3D.new()
		border_inst.mesh = border_quad
		border_inst.material_override = border_mat
		border_inst.position = Vector3(0, ICON_Y + 0.01, 0.001)
		border_inst.rotation.z = PI * 0.25
		sign_root.add_child(border_inst)
		# Icon on the sign
		var icon_label := Label3D.new()
		icon_label.text = cfg["icon"]
		icon_label.font_size = 36
		icon_label.pixel_size = 0.002
		icon_label.modulate = Color(0.1, 0.1, 0.1)
		icon_label.no_depth_test = true
		icon_label.render_priority = 14
		icon_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		icon_label.position = Vector3(0, ICON_Y + 0.01, -0.002)
		sign_root.add_child(icon_label)
		# Text label below sign — hidden by default, shown on hover/zoom
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
		text_label.position = Vector3(0, ICON_Y - 0.04, 0)
		text_label.visible = false
		sign_root.add_child(text_label)
		_labels.append(text_label)
		# Hover detection
		var area := Area3D.new()
		var coll := CollisionShape3D.new()
		var shape := BoxShape3D.new()
		shape.size = Vector3(SIGN_SIZE * 1.5, SIGN_SIZE * 1.5 + POLE_HEIGHT, SIGN_SIZE * 1.5)
		coll.shape = shape
		area.add_child(coll)
		area.position = Vector3(0, ICON_Y, 0)
		area.input_ray_pickable = true
		var lbl_ref := text_label
		area.mouse_entered.connect(
			func() -> void:
				lbl_ref.visible = true
				lbl_ref.set_meta("hovered", true)
		)
		area.mouse_exited.connect(
			func() -> void: lbl_ref.remove_meta("hovered")
			# _process will hide if not zoomed in
		)
		sign_root.add_child(area)
		# Attention-grabbing animation: gentle bob + scale pulse
		_animate_sign(sign_root)
		x_offset += 0.18


func _animate_sign(node: Node3D) -> void:
	var base_y: float = node.position.y
	var tw := create_tween()
	tw.set_loops()
	# Bob up and down
	tw.tween_property(node, "position:y", base_y + 0.02, 0.8).set_ease(Tween.EASE_IN_OUT).set_trans(
		Tween.TRANS_SINE
	)
	tw.tween_property(node, "position:y", base_y, 0.8).set_ease(Tween.EASE_IN_OUT).set_trans(
		Tween.TRANS_SINE
	)
	# Separate scale pulse
	var tw2 := create_tween()
	tw2.set_loops()
	(
		tw2
		. tween_property(node, "scale", Vector3(1.15, 1.15, 1.15), 0.6)
		. set_ease(Tween.EASE_IN_OUT)
		. set_trans(Tween.TRANS_SINE)
	)
	tw2.tween_property(node, "scale", Vector3.ONE, 0.6).set_ease(Tween.EASE_IN_OUT).set_trans(
		Tween.TRANS_SINE
	)
