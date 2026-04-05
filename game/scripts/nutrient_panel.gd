extends PanelContainer
## 2D UI panel showing per-layer soil nutrient bars.
## Displayed on CanvasLayer when soil cutaway is open.

const NUTRIENT_BARS := {
	"NO3":
	{"color": Color(0.17, 0.63, 0.17), "max": 5.0, "opt_min": 1.0, "opt_max": 5.0, "unit": "g/m²"},
	"NH4":
	{"color": Color(0.6, 0.87, 0.54), "max": 3.0, "opt_min": 0.3, "opt_max": 3.0, "unit": "g/m²"},
	"P":
	{"color": Color(0.58, 0.4, 0.74), "max": 2.0, "opt_min": 0.2, "opt_max": 2.0, "unit": "g/m²"},
	"SOM":
	{
		"color": Color(0.55, 0.34, 0.29),
		"max": 500.0,
		"opt_min": 50.0,
		"opt_max": 500.0,
		"unit": "gC/m²"
	},
	"Water":
	{
		"color": Color(0.12, 0.47, 0.71),
		"max": 0.45,
		"opt_min": 0.08,
		"opt_max": 0.35,
		"unit": "m³/m³"
	},
	"pH": {"color": Color(0.5, 0.5, 0.5), "max": 9.0, "opt_min": 5.5, "opt_max": 7.5, "unit": ""},
	"Microbe":
	{"color": Color(1.0, 0.5, 0.05), "max": 50.0, "opt_min": 5.0, "opt_max": 50.0, "unit": "gC/m²"},
}
const BAR_STRESS := Color(0.9, 0.25, 0.2)
const BAR_MARGINAL := Color(0.95, 0.75, 0.2)
const BAR_OK := Color(0.2, 0.7, 0.3)


func show_layers(layers_data: Array[Dictionary]) -> void:
	_clear()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.06, 0.06, 0.08, 0.92)
	style.corner_radius_top_left = 6
	style.corner_radius_top_right = 6
	style.corner_radius_bottom_left = 6
	style.corner_radius_bottom_right = 6
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 8
	style.content_margin_bottom = 8
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.border_color = Color(0.3, 0.3, 0.35, 0.5)
	add_theme_stylebox_override("panel", style)
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)
	add_child(vbox)
	for i in range(layers_data.size()):
		if i > 0:
			var sep := HSeparator.new()
			(
				sep
				. add_theme_stylebox_override(
					"separator",
					_make_sep_style(),
				)
			)
			vbox.add_child(sep)
		var layer: Dictionary = layers_data[i]
		var depth: String = layer.get("depth_label", "Layer %d" % (i + 1))
		var header := Label.new()
		header.text = depth
		header.add_theme_font_size_override("font_size", 12)
		header.add_theme_color_override("font_color", Color(0.7, 0.7, 0.75))
		vbox.add_child(header)
		var vals: Dictionary = layer.get("values", {})
		for key: String in NUTRIENT_BARS:
			var cfg: Dictionary = NUTRIENT_BARS[key]
			var val: float = vals.get(key, 0.0)
			_add_bar_row(vbox, key, val, cfg)


func hide_panel() -> void:
	_clear()
	visible = false


func _clear() -> void:
	for child in get_children():
		child.queue_free()


func _add_bar_row(parent: VBoxContainer, label: String, val: float, cfg: Dictionary) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	# Label
	var lbl := Label.new()
	lbl.text = label
	lbl.add_theme_font_size_override("font_size", 11)
	lbl.add_theme_color_override("font_color", cfg["color"])
	lbl.custom_minimum_size.x = 50
	row.add_child(lbl)
	# Bar background (shows optimal range)
	var bar_bg := Control.new()
	bar_bg.custom_minimum_size = Vector2(120, 12)
	# Optimal range background
	var opt_bg := ColorRect.new()
	var max_val: float = cfg["max"]
	var opt_min: float = cfg["opt_min"]
	var opt_max: float = cfg["opt_max"]
	var opt_min_frac: float = opt_min / max_val
	var opt_max_frac: float = opt_max / max_val
	if label == "pH":
		# pH: optimal range centered, show as green zone
		opt_min_frac = (opt_min - 4.0) / (9.0 - 4.0)
		opt_max_frac = (opt_max - 4.0) / (9.0 - 4.0)
	opt_bg.color = Color(0.15, 0.35, 0.15, 0.4)
	opt_bg.position = Vector2(opt_min_frac * 120, 0)
	opt_bg.size = Vector2((opt_max_frac - opt_min_frac) * 120, 12)
	bar_bg.add_child(opt_bg)
	# Value bar fill
	var bar_fill := ColorRect.new()
	var bar_frac: float = clampf(val / maxf(max_val, 0.001), 0.0, 1.0)
	if label == "pH":
		bar_frac = clampf((val - 4.0) / (9.0 - 4.0), 0.0, 1.0)
	var bar_color: Color = _stress_color(label, val, opt_min, opt_max)
	bar_fill.color = bar_color
	bar_fill.size = Vector2(bar_frac * 120, 12)
	bar_bg.add_child(bar_fill)
	# Outline
	var outline := ReferenceRect.new()
	outline.size = Vector2(120, 12)
	outline.border_color = Color(0.35, 0.35, 0.4, 0.6)
	outline.border_width = 1.0
	outline.editor_only = false
	bar_bg.add_child(outline)
	row.add_child(bar_bg)
	# Value text
	var val_lbl := Label.new()
	var unit: String = cfg["unit"]
	if label == "pH":
		val_lbl.text = "%.1f" % val
	elif val >= 100.0:
		val_lbl.text = "%.0f %s" % [val, unit]
	else:
		val_lbl.text = "%.1f %s" % [val, unit]
	val_lbl.add_theme_font_size_override("font_size", 10)
	val_lbl.add_theme_color_override("font_color", Color(0.8, 0.8, 0.85))
	val_lbl.custom_minimum_size.x = 65
	row.add_child(val_lbl)
	parent.add_child(row)


static func _stress_color(key: String, val: float, opt_min: float, opt_max: float) -> Color:
	if key == "pH":
		if val < opt_min - 1.0 or val > opt_max + 1.0:
			return BAR_STRESS
		if val < opt_min or val > opt_max:
			return BAR_MARGINAL
		return BAR_OK
	if val < opt_min * 0.3:
		return BAR_STRESS
	if val < opt_min:
		return BAR_MARGINAL
	return BAR_OK


static func _make_sep_style() -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = Color(0.3, 0.3, 0.35, 0.3)
	s.content_margin_top = 1
	s.content_margin_bottom = 1
	return s
