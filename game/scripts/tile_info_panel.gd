extends PanelContainer
## Tile info popup showing historical sparkline graphs.
## Displayed on CanvasLayer when a tile is selected.

const Sparkline = preload("res://scripts/sparkline.gd")

## Graph configs: key matches _daily_history fields
const GRAPHS := {
	"lai": {"label": "LAI", "unit": "m²/m²", "color": Color(0.2, 0.72, 0.2)},
	"grain_g_m2": {"label": "Grain", "unit": "g/m²", "color": Color(0.85, 0.7, 0.2)},
	"water_stress": {"label": "Water stress", "unit": "", "color": Color(0.85, 0.3, 0.2)},
	"theta_surface": {"label": "Soil water", "unit": "m³/m³", "color": Color(0.3, 0.75, 0.9)},
	"n_available": {"label": "N available", "unit": "g/m²", "color": Color(0.17, 0.63, 0.17)},
}

var _sparklines: Dictionary = {}


func show_history(history: Array, soil_type: String, crop_key: String) -> void:
	_clear()
	add_theme_stylebox_override("panel", UiTheme.create_panel_style())

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	add_child(vbox)

	# Title
	var title := Label.new()
	var title_text := crop_key.to_upper() if not crop_key.is_empty() else "EMPTY"
	title.text = "%s — %s" % [title_text, soil_type.to_upper()]
	title.add_theme_font_size_override("font_size", 12)
	title.add_theme_color_override("font_color", UiTheme.HEADER_COLOR)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(title)

	# Day count or no-data message
	var days_label := Label.new()
	if history.is_empty():
		days_label.text = "Step days to see history"
	else:
		days_label.text = "%d days" % history.size()
	days_label.add_theme_font_size_override("font_size", 10)
	days_label.add_theme_color_override("font_color", UiTheme.MUTED_COLOR)
	days_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(days_label)

	if history.is_empty():
		visible = true
		return

	# Collect stage transition days for markers
	var stage_days := _find_stage_transitions(history)

	# Build sparklines
	_sparklines.clear()
	for key: String in GRAPHS:
		var cfg: Dictionary = GRAPHS[key]
		var spark := Control.new()
		spark.set_script(Sparkline)
		spark.setup(cfg["label"], cfg["unit"], cfg["color"], 36.0)
		var data := _extract_series(history, key)
		spark.set_data(data, stage_days)
		_sparklines[key] = spark
		vbox.add_child(spark)

	visible = true


func update_history(history: Array) -> void:
	## Update existing sparklines with new data (avoids full rebuild).
	if _sparklines.is_empty():
		return
	var stage_days := _find_stage_transitions(history)
	for key: String in GRAPHS:
		if _sparklines.has(key):
			var data := _extract_series(history, key)
			_sparklines[key].set_data(data, stage_days)


func hide_panel() -> void:
	_clear()
	visible = false


func _clear() -> void:
	_sparklines.clear()
	for child in get_children():
		child.queue_free()


static func _extract_series(history: Array, key: String) -> PackedFloat64Array:
	var arr := PackedFloat64Array()
	for entry: Dictionary in history:
		arr.append(entry.get(key, 0.0))
	return arr


static func _find_stage_transitions(history: Array) -> PackedInt32Array:
	var transitions := PackedInt32Array()
	var prev_stage := ""
	for i in range(history.size()):
		var stage: String = history[i].get("crop_stage", "")
		if stage != prev_stage and not prev_stage.is_empty():
			transitions.append(i)
		prev_stage = stage
	return transitions
