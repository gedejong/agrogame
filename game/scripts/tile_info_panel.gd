extends PanelContainer
## Tile info popup showing historical sparkline graphs.
## Displayed on CanvasLayer when a tile is selected.

const Sparkline = preload("res://scripts/sparkline.gd")

## Graph configs: key matches _daily_history fields.
## "mass_type": "mass" for g/m²↔kg/ha conversion, "" for no conversion.
const GRAPHS := {
	"lai": {"label": "LAI", "unit": "m²/m²", "mass_type": "", "color": UiTheme.ACCENT_GREEN},
	"grain_g_m2": {"label": "Grain", "unit": "", "mass_type": "mass", "color": UiTheme.ACCENT_GOLD},
	"water_stress":
	{"label": "Water stress", "unit": "", "mass_type": "", "color": UiTheme.ACCENT_RED},
	"theta_surface":
	{"label": "Soil water", "unit": "m³/m³", "mass_type": "", "color": UiTheme.SUBSTANCE_WATER},
	"n_available":
	{"label": "N available", "unit": "", "mass_type": "mass", "color": UiTheme.SUBSTANCE_NO3},
	"redox_eh_surface":
	{"label": "Redox Eh", "unit": "mV", "mass_type": "", "color": UiTheme.SUBSTANCE_REDOX},
}

var _sparklines: Dictionary = {}


func show_history(history: Array, soil_type: String, crop_key: String) -> void:
	_clear()
	var style := UiTheme.create_panel_style(true)
	style.content_margin_left = 5
	style.content_margin_right = 5
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	add_theme_stylebox_override("panel", style)
	UiTheme.add_blur_bg(self)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	add_child(vbox)

	# Title
	var title := Label.new()
	var title_text := crop_key.capitalize() if not crop_key.is_empty() else "Empty"
	title.text = "%s — %s" % [title_text, soil_type]
	title.uppercase = true
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
		var display_unit: String = cfg.get("unit", "")
		if cfg.get("mass_type", "") == "mass":
			display_unit = UiTheme.mass_label()
		spark.setup(cfg["label"], display_unit, cfg["color"], 36.0)
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
