extends VBoxContainer
## Per-layer SOM carbon stock, with an optional three-pool breakdown.
## API pool arrays pass through kgC/ha from the SOM model.
## Pool stocks are not nutrient-stress or soil-health scores.

const POOL_FIELDS := {
	"Labile": "som_labile_c",
	"Intermediate": "som_intermediate_c",
	"Stable": "som_stable_c",
}


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
		"Carbon held in this layer's labile, intermediate and stable SOM pools.\n"
		+ "This is a carbon stock, not total organic matter mass or a soil-health rating."
	)
	var title := Label.new()
	title.text = "Total organic carbon"
	title.add_theme_font_size_override("font_size", 10)
	title.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	add_child(title)

	var total: float = 0.0
	var complete: bool = true
	for pool: String in POOL_FIELDS:
		if not _valid_carbon(pools.get(pool)):
			complete = false
		else:
			total += float(pools[pool])
	var value := Label.new()
	value.name = "TotalCarbonValue"
	value.text = _format_carbon(total) if complete else "Unavailable"
	value.add_theme_font_size_override("font_size", 12)
	value.add_theme_color_override("font_color", UiTheme.TEXT_PRIMARY)
	add_child(value)

	var toggle := Button.new()
	toggle.name = "TogglePools"
	toggle.text = "▸ Pool breakdown"
	toggle.toggle_mode = true
	toggle.flat = true
	toggle.alignment = HORIZONTAL_ALIGNMENT_LEFT
	toggle.add_theme_font_size_override("font_size", 10)
	toggle.tooltip_text = "Show or hide carbon in each SOM pool"
	UiTheme.style_button(toggle)
	add_child(toggle)
	var details := VBoxContainer.new()
	details.name = "PoolBreakdown"
	details.visible = false
	add_child(details)
	for pool: String in POOL_FIELDS:
		_add_pool_row(details, pool, pools.get(pool))
	toggle.toggled.connect(
		func(expanded: bool) -> void:
			details.visible = expanded
			toggle.text = ("▾ " if expanded else "▸ ") + "Pool breakdown"
	)


func _add_pool_row(parent: VBoxContainer, pool: String, carbon: Variant) -> void:
	var row := HBoxContainer.new()
	row.name = pool
	var label := Label.new()
	label.text = pool
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("font_size", 10)
	label.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	row.add_child(label)
	var value := Label.new()
	value.name = "Value"
	value.text = _format_carbon(float(carbon)) if _valid_carbon(carbon) else "Unavailable"
	value.add_theme_font_size_override("font_size", 10)
	value.add_theme_color_override("font_color", UiTheme.TEXT_PRIMARY)
	row.add_child(value)
	parent.add_child(row)
