class_name StressIcons
extends Node3D
## Floating warning icons above tiles for weather damage events.
## Shows frost (snowflake), heat (sun), waterlogging (drops) icons
## with labels when the simulation reports damage.

const ICON_Y := 0.6
const ICON_SIZE := 0.003
const FADE_DURATION := 0.3

## Event types that trigger stress icons.
const STRESS_EVENTS := {
	"FrostDamageApplied":
	{
		"icon": "❄",
		"label": "Frost",
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
		_fade_out_and_free(node)
		_icons.erase(key)
	# Create/update icons for stressed tiles
	for tile_idx: int in tile_stresses:
		var etypes: Array = tile_stresses[tile_idx]
		var key: String = str(tile_idx)
		if _icons.has(key):
			_update_icon(_icons[key], etypes)
		else:
			var pos: Vector3 = tile_meshes[tile_idx].position
			var icon := _create_icon(pos, etypes)
			add_child(icon)
			_icons[key] = icon


func clear_icons() -> void:
	for key: String in _icons:
		_icons[key].queue_free()
	_icons.clear()


func _create_icon(pos: Vector3, etypes: Array) -> Node3D:
	var container := Node3D.new()
	container.position = Vector3(pos.x, pos.y + ICON_Y, pos.z)
	_build_icon_content(container, etypes)
	return container


func _update_icon(container: Node3D, etypes: Array) -> void:
	for child in container.get_children():
		child.queue_free()
	_build_icon_content(container, etypes)


func _build_icon_content(container: Node3D, etypes: Array) -> void:
	var x_offset := 0.0
	for etype: String in etypes:
		if not STRESS_EVENTS.has(etype):
			continue
		var cfg: Dictionary = STRESS_EVENTS[etype]
		# Icon character
		var icon_label := Label3D.new()
		icon_label.text = cfg["icon"]
		icon_label.font_size = 48
		icon_label.pixel_size = ICON_SIZE
		icon_label.modulate = cfg["color"]
		icon_label.outline_size = 8
		icon_label.outline_modulate = Color(0, 0, 0, 0.7)
		icon_label.no_depth_test = true
		icon_label.render_priority = 12
		icon_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		icon_label.position = Vector3(x_offset, 0.05, 0)
		container.add_child(icon_label)
		# Text label below
		var text_label := Label3D.new()
		text_label.text = cfg["label"]
		text_label.font_size = 24
		text_label.pixel_size = ICON_SIZE * 0.8
		text_label.modulate = cfg["color"]
		text_label.outline_size = 6
		text_label.outline_modulate = Color(0, 0, 0, 0.6)
		text_label.no_depth_test = true
		text_label.render_priority = 12
		text_label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
		text_label.position = Vector3(x_offset, -0.02, 0)
		container.add_child(text_label)
		x_offset += 0.15


func _fade_out_and_free(node: Node3D) -> void:
	var tw := create_tween()
	tw.tween_property(node, "modulate:a", 0.0, FADE_DURATION)
	tw.tween_callback(node.queue_free)
