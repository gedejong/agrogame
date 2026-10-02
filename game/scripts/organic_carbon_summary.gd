extends VBoxContainer
## Per-layer SOM carbon stock, with an optional three-pool breakdown.
## API pool arrays pass through kgC/ha from the SOM model.
## Pool stocks are not nutrient-stress or soil-health scores.

const POOL_FIELDS := {
	"Labile": "som_labile_c",
	"Intermediate": "som_intermediate_c",
	"Stable": "som_stable_c",
}
const TRACK_WIDTH := 100.0
const POOL_OPACITY := [1.0, 0.65, 0.35]


static func pools_for_layer(soil_state: Dictionary, layer_idx: int) -> Dictionary:
	var pools: Dictionary = {}
	if layer_idx < 0:
		return pools
	for pool: String in POOL_FIELDS:
		var values: Variant = soil_state.get(POOL_FIELDS[pool], [])
		if values is Array and layer_idx < values.size():
			if _valid_carbon(values[layer_idx]):
				pools[pool] = float(values[layer_idx])
	return pools


static func _valid_carbon(value: Variant) -> bool:
	return (value is float or value is int) and is_finite(float(value)) and value >= 0.0


static func _format_carbon(value: float) -> String:
	return "%.1f %s" % [UiTheme.to_display_mass(value), UiTheme.carbon_label()]


func show_pools(pools: Dictionary) -> void:
	for child: Node in get_children():
		remove_child(child)
		child.queue_free()
	add_theme_constant_override("separation", 2)
	tooltip_text = (
		"Total organic carbon in this layer. Expand the arrow to see the three SOM pools.\n"
		+ "Gold segments show labile / intermediate / stable shares, not soil health.\n"
		+ "Carbon stock is not total organic matter mass."
	)
	var total: float = 0.0
	var complete: bool = true
	for pool: String in POOL_FIELDS:
		if not _valid_carbon(pools.get(pool)):
			complete = false
		else:
			total += float(pools[pool])
	var row := HBoxContainer.new()
	row.name = "TotalRow"
	row.add_theme_constant_override("separation", 6)
	add_child(row)
	var icon := TextureRect.new()
	icon.texture = preload("res://assets/icons/icon_som.svg")
	icon.custom_minimum_size = Vector2(14, 14)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	row.add_child(icon)
	var label := Label.new()
	label.text = "C total"
	label.custom_minimum_size.x = 40
	label.add_theme_font_size_override("font_size", 10)
	label.add_theme_color_override("font_color", UiTheme.SUBSTANCE_CARBON)
	row.add_child(label)
	_add_composition_track(row, pools, total, complete)
	var value := Label.new()
	value.name = "TotalCarbonValue"
	value.text = _format_carbon(total) if complete else "Unavailable"
	value.custom_minimum_size.x = 70
	value.add_theme_font_size_override("font_size", 9)
	value.add_theme_color_override("font_color", UiTheme.TEXT_PRIMARY)
	row.add_child(value)
	var toggle := Button.new()
	toggle.name = "TogglePools"
	toggle.text = "▸"
	toggle.toggle_mode = true
	toggle.flat = true
	toggle.add_theme_font_size_override("font_size", 10)
	toggle.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	toggle.add_theme_color_override("font_hover_color", UiTheme.TEXT_PRIMARY)
	toggle.add_theme_stylebox_override("normal", StyleBoxEmpty.new())
	toggle.add_theme_stylebox_override("hover", StyleBoxEmpty.new())
	toggle.add_theme_stylebox_override("pressed", StyleBoxEmpty.new())
	toggle.tooltip_text = "Show or hide organic carbon pool breakdown"
	row.add_child(toggle)
	var details := VBoxContainer.new()
	details.name = "PoolBreakdown"
	details.visible = false
	add_child(details)
	for pool: String in POOL_FIELDS:
		_add_pool_row(details, pool, pools.get(pool), total if complete else 0.0)
	toggle.toggled.connect(
		func(expanded: bool) -> void:
			details.visible = expanded
			toggle.text = "▾" if expanded else "▸"
	)


func _add_composition_track(
	parent: HBoxContainer, pools: Dictionary, total: float, complete: bool
) -> void:
	var track := Control.new()
	track.name = "CompositionTrack"
	track.custom_minimum_size = Vector2(TRACK_WIDTH, 12)
	var background := ColorRect.new()
	background.color = UiTheme.TRACK_BG
	background.size = Vector2(TRACK_WIDTH, 12)
	track.add_child(background)
	if complete and total > 0.0:
		var offset: float = 0.0
		for i in range(POOL_FIELDS.size()):
			var pool: String = POOL_FIELDS.keys()[i]
			var segment := ColorRect.new()
			segment.name = pool
			segment.color = UiTheme.SUBSTANCE_CARBON
			segment.color.a *= POOL_OPACITY[i]
			segment.position = Vector2(offset, 3)
			segment.size = Vector2(float(pools[pool]) / total * TRACK_WIDTH, 5)
			offset += segment.size.x
			track.add_child(segment)
	var outline := ReferenceRect.new()
	outline.size = Vector2(TRACK_WIDTH, 12)
	outline.border_color = UiTheme.BORDER_COLOR
	outline.border_width = 1.0
	outline.editor_only = false
	track.add_child(outline)
	parent.add_child(track)


func _add_pool_row(parent: VBoxContainer, pool: String, carbon: Variant, total: float) -> void:
	var row := HBoxContainer.new()
	row.name = pool
	var indent := Control.new()
	indent.custom_minimum_size.x = 16
	row.add_child(indent)
	var label := Label.new()
	label.text = pool
	if total > 0.0 and _valid_carbon(carbon):
		label.text += "  %.1f%%" % (float(carbon) / total * 100.0)
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("font_size", 10)
	label.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	row.add_child(label)
	var value := Label.new()
	value.name = "Value"
	value.text = _format_carbon(float(carbon)) if _valid_carbon(carbon) else "Unavailable"
	value.add_theme_font_size_override("font_size", 9)
	value.add_theme_color_override("font_color", UiTheme.TEXT_PRIMARY)
	row.add_child(value)
	parent.add_child(row)
