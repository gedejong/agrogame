extends PanelContainer
## 2D UI panel showing per-layer soil nutrient bars.
## Styled per art guide: glassmorphism dark slate-navy panels.

## Max/optimal values calibrated from simulation output (maize on loam, 150 days).
## Values stored in g/m² (simulation native unit); converted at display time.
## "mass_type": "mass" for g/m²↔kg/ha, "carbon" for gC/m²↔kgC/ha, "" for no conversion.
const NUTRIENT_BARS := {
	"NO₃":
	{
		"color": UiTheme.SUBSTANCE_NO3,
		"icon": "res://assets/icons/icon_no3.svg",
		"max": 100.0,
		"opt_min": 5.0,
		"opt_max": 60.0,
		"mass_type": "mass",
	},
	"NH₄":
	{
		"color": UiTheme.SUBSTANCE_NH4,
		"icon": "res://assets/icons/icon_nh4.svg",
		"max": 120.0,
		"opt_min": 3.0,
		"opt_max": 80.0,
		"mass_type": "mass",
	},
	"P":
	{
		"color": UiTheme.SUBSTANCE_PHOSPHORUS,
		"icon": "res://assets/icons/icon_p.svg",
		"max": 25.0,
		"opt_min": 5.0,
		"opt_max": 20.0,
		"mass_type": "mass",
	},
	"SOM":
	{
		"color": UiTheme.SUBSTANCE_CARBON,
		"icon": "res://assets/icons/icon_som.svg",
		"max": 2500.0,
		"opt_min": 200.0,
		"opt_max": 2500.0,
		"mass_type": "carbon",
	},
	"Water":
	{
		"color": UiTheme.SUBSTANCE_WATER,
		"icon": "res://assets/icons/icon_water.svg",
		"max": 0.45,
		"opt_min": 0.10,
		"opt_max": 0.35,
		"mass_type": "",
		"unit": "m³/m³",
	},
	"pH":
	{
		"color": UiTheme.SUBSTANCE_PH,
		"icon": "res://assets/icons/icon_ph.svg",
		"max": 9.0,
		"opt_min": 5.5,
		"opt_max": 7.5,
		"mass_type": "",
		"unit": "",
	},
	"Microbe":
	{
		"color": UiTheme.SUBSTANCE_MICROBE,
		"icon": "res://assets/icons/icon_microbe.svg",
		"max": 250.0,
		"opt_min": 50.0,
		"opt_max": 250.0,
		"mass_type": "carbon",
	},
}
## Functional accent colors per art guide
const BAR_STRESS := UiTheme.ACCENT_RED
const BAR_MARGINAL := UiTheme.ACCENT_GOLD
const BAR_OK := UiTheme.ACCENT_GREEN


func show_layers(layers_data: Array[Dictionary]) -> void:
	_clear()
	var style := UiTheme.create_panel_style(true)
	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	add_theme_stylebox_override("panel", style)
	UiTheme.add_blur_bg(self)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	add_child(vbox)

	# Title
	var title := Label.new()
	title.text = "Soil Analysis"
	title.uppercase = true
	title.add_theme_font_size_override("font_size", 11)
	title.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(title)

	for i in range(layers_data.size()):
		if i > 0:
			_add_separator(vbox)
		var layer: Dictionary = layers_data[i]
		var depth: String = layer.get("depth_label", "Layer %d" % (i + 1))
		# Layer header
		var header := Label.new()
		header.text = "▸ %s" % depth
		header.add_theme_font_size_override("font_size", 11)
		header.add_theme_color_override("font_color", UiTheme.HEADER_COLOR)
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


func _add_separator(parent: VBoxContainer) -> void:
	var sep := HSeparator.new()
	var s := StyleBoxFlat.new()
	s.bg_color = UiTheme.SEPARATOR_COLOR
	s.content_margin_top = 3
	s.content_margin_bottom = 3
	sep.add_theme_stylebox_override("separator", s)
	parent.add_child(sep)


func _add_bar_row(parent: VBoxContainer, label: String, val: float, cfg: Dictionary) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var track_w := 100
	var track_h := 12
	var bar_h := 5
	var bar_y: int = (track_h - bar_h) / 2

	# Icon (12×12)
	var icon_path: String = cfg.get("icon", "")
	if not icon_path.is_empty() and ResourceLoader.exists(icon_path):
		var icon := TextureRect.new()
		icon.texture = load(icon_path)
		icon.custom_minimum_size = Vector2(12, 12)
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		row.add_child(icon)
	# Label — nutrient name
	var lbl := Label.new()
	lbl.text = label
	lbl.add_theme_font_size_override("font_size", 10)
	lbl.add_theme_color_override("font_color", cfg["color"])
	lbl.custom_minimum_size.x = 40
	row.add_child(lbl)

	# Bar track
	var bar_bg := Control.new()
	bar_bg.custom_minimum_size = Vector2(track_w, track_h)

	# Track background
	var track := ColorRect.new()
	track.color = UiTheme.TRACK_BG
	track.size = Vector2(track_w, track_h)
	bar_bg.add_child(track)

	# Optimal range zone — full track height
	var max_val: float = cfg["max"]
	var opt_min: float = cfg["opt_min"]
	var opt_max: float = cfg["opt_max"]
	var opt_min_frac: float = opt_min / max_val
	var opt_max_frac: float = opt_max / max_val
	if label == "pH":
		opt_min_frac = (opt_min - 4.0) / (9.0 - 4.0)
		opt_max_frac = (opt_max - 4.0) / (9.0 - 4.0)
	var opt_bg := ColorRect.new()
	opt_bg.color = UiTheme.OPT_ZONE
	opt_bg.position = Vector2(opt_min_frac * track_w, 0)
	opt_bg.size = Vector2((opt_max_frac - opt_min_frac) * track_w, track_h)
	bar_bg.add_child(opt_bg)

	# Value bar — thin, centered
	var bar_frac: float = clampf(val / maxf(max_val, 0.001), 0.0, 1.0)
	if label == "pH":
		bar_frac = clampf((val - 4.0) / (9.0 - 4.0), 0.0, 1.0)
	var bar_color: Color = _stress_color(label, val, opt_min, opt_max)
	var bar_fill := ColorRect.new()
	bar_fill.color = bar_color
	bar_fill.position = Vector2(0, bar_y)
	bar_fill.size = Vector2(maxf(bar_frac * track_w, 1.0), bar_h)
	bar_bg.add_child(bar_fill)

	# Track outline
	var outline := ReferenceRect.new()
	outline.size = Vector2(track_w, track_h)
	outline.border_color = UiTheme.BORDER_COLOR
	outline.border_width = 1.0
	outline.editor_only = false
	bar_bg.add_child(outline)
	row.add_child(bar_bg)

	# Value text — convert to active display unit
	var val_lbl := Label.new()
	var mass_type: String = cfg.get("mass_type", "")
	var unit: String = cfg.get("unit", "")
	var display_val: float = val
	if mass_type == "mass":
		display_val = UiTheme.to_display_mass_from_gm2(val)
		unit = UiTheme.mass_label()
	elif mass_type == "carbon":
		display_val = UiTheme.to_display_mass_from_gm2(val)
		unit = UiTheme.carbon_label()
	if label == "pH":
		val_lbl.text = "%.1f" % val
	elif display_val >= 100.0:
		val_lbl.text = "%.0f" % display_val
	elif display_val >= 1.0:
		val_lbl.text = "%.1f" % display_val
	else:
		val_lbl.text = "%.2f" % display_val
	if not unit.is_empty():
		val_lbl.text += " " + unit
	val_lbl.add_theme_font_size_override("font_size", 9)
	val_lbl.add_theme_color_override("font_color", UiTheme.VALUE_COLOR)
	val_lbl.custom_minimum_size.x = 70
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
