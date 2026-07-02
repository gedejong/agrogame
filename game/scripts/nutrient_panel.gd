extends PanelContainer
## 2D UI panel showing per-layer soil nutrient bars.
## Styled per art guide: glassmorphism dark slate-navy panels.

## Emitted when user clicks a cycle filter or toggle button.
signal flow_filter_changed(filter_name: String)
signal flow_toggle_changed(visible: bool)
signal layer_selected(layer_idx: int)

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
		"tooltip": "Nitrate — mobile plant nutrient, easily leached by rain",
	},
	"NH₄":
	{
		"color": UiTheme.SUBSTANCE_NH4,
		"icon": "res://assets/icons/icon_nh4.svg",
		"max": 120.0,
		"opt_min": 3.0,
		"opt_max": 80.0,
		"mass_type": "mass",
		"tooltip": "Ammonium — held by clay, converted to nitrate by bacteria",
	},
	"P":
	{
		"color": UiTheme.SUBSTANCE_PHOSPHORUS,
		"icon": "res://assets/icons/icon_p.svg",
		"max": 25.0,
		"opt_min": 5.0,
		"opt_max": 20.0,
		"mass_type": "mass",
		"tooltip": "Phosphorus — essential for roots and energy, easily locked up in soil",
	},
	"SOM":
	{
		"color": UiTheme.SUBSTANCE_CARBON,
		"icon": "res://assets/icons/icon_som.svg",
		"max": 2500.0,
		"opt_min": 200.0,
		"opt_max": 2500.0,
		"mass_type": "carbon",
		"tooltip": "Soil organic matter — feeds microbes, improves structure and water holding",
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
		"tooltip": "Soil water content — too low causes drought, too high causes waterlogging",
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
		"tooltip": "Soil acidity — most crops prefer pH 5.5-7.5; affects nutrient availability",
	},
	"Microbe":
	{
		"color": UiTheme.SUBSTANCE_MICROBE,
		"icon": "res://assets/icons/icon_microbe.svg",
		"max": 250.0,
		"opt_min": 50.0,
		"opt_max": 250.0,
		"mass_type": "carbon",
		"tooltip": "Microbial biomass — decomposers that recycle nutrients from organic matter",
	},
	"MicrobeN":
	{
		"color": UiTheme.SUBSTANCE_MICROBE,
		"icon": "",
		"icon_glyph": "N",
		"max": 40.0,
		"opt_min": 5.0,
		"opt_max": 40.0,
		"mass_type": "",
		"unit": "kg/ha",
		"tooltip":
		"Microbial biomass N — nitrogen immobilised in decomposers, released on turnover",
	},
	"Fungal":
	{
		"color": Color(0.60, 0.50, 0.30, 0.8),
		"icon": "",
		"icon_glyph": "⚘",
		"max": 1.0,
		"opt_min": 0.35,
		"opt_max": 0.75,
		"mass_type": "",
		"unit": "",
		"tooltip":
		(
			"Fungal fraction of microbial biomass (0-1).\n"
			+ "Higher = fungal-dominated (no-till, high residue);\n"
			+ "lower = bacterial-dominated (tilled, high N)."
		),
	},
	"Fe":
	{
		"color": Color(0.75, 0.45, 0.20, 0.8),
		"icon": "",
		"icon_glyph": "Fe",
		"max": 20.0,
		"opt_min": 4.5,
		"opt_max": 20.0,
		"mass_type": "",
		"unit": "ppm",
		"tooltip": "Iron — essential for chlorophyll; deficiency causes yellowing (chlorosis)",
	},
	"Zn":
	{
		"color": Color(0.45, 0.55, 0.70, 0.8),
		"icon": "",
		"icon_glyph": "Zn",
		"max": 5.0,
		"opt_min": 0.8,
		"opt_max": 5.0,
		"mass_type": "",
		"unit": "ppm",
		"tooltip": "Zinc — needed for enzymes and growth hormones; deficiency stunts growth",
	},
	"Mn":
	{
		"color": Color(0.50, 0.35, 0.60, 0.8),
		"icon": "",
		"icon_glyph": "Mn",
		"max": 50.0,
		"opt_min": 1.0,
		"opt_max": 50.0,
		"mass_type": "",
		"unit": "ppm",
		"tooltip": "Manganese — activates enzymes in photosynthesis; pH-sensitive availability",
	},
	"Eh":
	{
		"color": UiTheme.SUBSTANCE_REDOX,
		"icon": "",
		"icon_glyph": "\u26a1",
		"max": 450.0,
		"opt_min": 200.0,
		"opt_max": 450.0,
		"mass_type": "",
		"unit": "mV",
		"tooltip":
		(
			"Redox potential — measures oxygen availability.\n"
			+ "Green (>200): aerobic. Yellow (0-200): suboxic.\n"
			+ "Red (<0): anaerobic, methane risk."
		),
	},
	"MWD":
	{
		"color": UiTheme.SUBSTANCE_AGGREGATE,
		"icon": "",
		"icon_glyph": "\u2b22",
		"max": 2.5,
		"opt_min": 1.5,
		"opt_max": 2.5,
		"mass_type": "",
		"unit": "mm",
		"tooltip":
		(
			"Mean Weight Diameter — aggregate stability indicator.\n"
			+ "Green (>1.5): good structure. Yellow (0.5-1.5): moderate.\n"
			+ "Red (<0.5): degraded. Tillage destroys, roots rebuild."
		),
	},
}
## Functional accent colors per art guide
const BAR_STRESS := UiTheme.ACCENT_RED
const BAR_MARGINAL := UiTheme.ACCENT_GOLD
const BAR_OK := UiTheme.ACCENT_GREEN

## Eh display range and zone thresholds (mV).
const EH_MIN_MV := -300.0
const EH_MAX_MV := 450.0
const EH_RANGE_MV := EH_MAX_MV - EH_MIN_MV
const EH_OXIC_THRESHOLD := 200.0
const EH_ANOXIC_THRESHOLD := 0.0

var _flow_visible := true
var _cycle_label: Label = null
var _filter_buttons: Dictionary = {}
var _active_filter: String = "all"
var _layer_bodies: Array[VBoxContainer] = []
var _layer_headers: Array[Button] = []
var _all_expanded := false


func show_layers(layers_data: Array[Dictionary], biomass: Dictionary = {}) -> void:
	_clear()
	var style := UiTheme.create_panel_style(true)
	style.content_margin_left = 5
	style.content_margin_right = 5
	style.content_margin_top = 5
	style.content_margin_bottom = 5
	add_theme_stylebox_override("panel", style)
	UiTheme.add_blur_bg(self)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 10)
	margin.add_theme_constant_override("margin_right", 10)
	margin.add_theme_constant_override("margin_top", 8)
	margin.add_theme_constant_override("margin_bottom", 8)
	add_child(margin)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 6)
	vbox.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	margin.add_child(vbox)

	# Title row with Expand All button
	var title_row := HBoxContainer.new()
	var title := Label.new()
	title.text = "Soil Analysis"
	title.uppercase = true
	title.add_theme_font_size_override("font_size", 11)
	title.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_row.add_child(title)
	var expand_btn := Button.new()
	expand_btn.text = "Expand All"
	expand_btn.add_theme_font_size_override("font_size", 9)
	UiTheme.style_button(expand_btn)
	expand_btn.pressed.connect(_on_expand_all)
	title_row.add_child(expand_btn)
	vbox.add_child(title_row)

	# Plant biomass split — root vs stem (#317)
	if not biomass.is_empty():
		_build_biomass_row(vbox, biomass)
		_add_separator(vbox)

	# Flow cycle filter row
	_build_cycle_row(vbox)
	_add_separator(vbox)

	# Accordion layers — only layer 0 expanded by default
	_layer_bodies.clear()
	_layer_headers.clear()
	for i in range(layers_data.size()):
		if i > 0:
			_add_separator(vbox)
		var layer: Dictionary = layers_data[i]
		var depth: String = layer.get("depth_label", "Layer %d" % (i + 1))
		# Clickable layer header
		var header := Button.new()
		header.text = "▾ %s" % depth if i == 0 else "▸ %s" % depth
		header.add_theme_font_size_override("font_size", 11)
		header.add_theme_color_override("font_color", UiTheme.HEADER_COLOR)
		header.flat = true
		header.alignment = HORIZONTAL_ALIGNMENT_LEFT
		header.pressed.connect(_on_layer_header.bind(i))
		_layer_headers.append(header)
		vbox.add_child(header)
		# Layer body (bars) — collapsible
		var body := VBoxContainer.new()
		body.add_theme_constant_override("separation", 2)
		body.visible = (i == 0)  # only top layer expanded
		var vals: Dictionary = layer.get("values", {})
		var acc: String = layer.get("dominant_acceptor", "O2")
		for key: String in NUTRIENT_BARS:
			var cfg: Dictionary = NUTRIENT_BARS[key]
			var val: float = vals.get(key, 0.0)
			var suffix: String = "  " + _format_acceptor(acc) if key == "Eh" else ""
			_add_bar_row(body, key, val, cfg, suffix)
		_layer_bodies.append(body)
		vbox.add_child(body)


func expand_layer(layer_idx: int) -> void:
	"""Expand a specific layer (e.g. from cutaway click)."""
	if layer_idx < 0 or layer_idx >= _layer_bodies.size():
		return
	_layer_bodies[layer_idx].visible = true
	_layer_headers[layer_idx].text = ("▾ " + _layer_headers[layer_idx].text.substr(2))


func _on_layer_header(layer_idx: int) -> void:
	var body: VBoxContainer = _layer_bodies[layer_idx]
	var header: Button = _layer_headers[layer_idx]
	var label_text: String = header.text.substr(2)  # strip arrow
	body.visible = not body.visible
	header.text = ("▾ " if body.visible else "▸ ") + label_text
	if body.visible:
		layer_selected.emit(layer_idx)


func _on_expand_all() -> void:
	_all_expanded = not _all_expanded
	for i in range(_layer_bodies.size()):
		_layer_bodies[i].visible = _all_expanded
		var label_text: String = _layer_headers[i].text.substr(2)
		var arrow: String = "▾ " if _all_expanded else "▸ "
		_layer_headers[i].text = arrow + label_text


func hide_panel() -> void:
	_clear()
	visible = false


func _clear() -> void:
	_layer_bodies.clear()
	_layer_headers.clear()
	for child in get_children():
		remove_child(child)
		child.queue_free()


func _add_separator(parent: VBoxContainer) -> void:
	var sep := HSeparator.new()
	var s := StyleBoxFlat.new()
	s.bg_color = UiTheme.SEPARATOR_COLOR
	s.content_margin_top = 5
	s.content_margin_bottom = 5
	sep.add_theme_stylebox_override("separator", s)
	parent.add_child(sep)


func _add_bar_row(
	parent: VBoxContainer, label: String, val: float, cfg: Dictionary, suffix: String = ""
) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var track_w := 100
	var track_h := 12
	var bar_h := 5
	var bar_y: int = (track_h - bar_h) / 2

	# Icon (12×12)
	# Icon column — fixed 14px wide for alignment
	var icon_container := Control.new()
	icon_container.custom_minimum_size = Vector2(14, 14)
	var icon_path: String = cfg.get("icon", "")
	if not icon_path.is_empty() and ResourceLoader.exists(icon_path):
		var icon := TextureRect.new()
		icon.texture = load(icon_path)
		icon.custom_minimum_size = Vector2(14, 14)
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon_container.add_child(icon)
	elif cfg.get("icon_glyph", ""):
		var glyph := Label.new()
		glyph.text = cfg["icon_glyph"]
		glyph.add_theme_font_size_override("font_size", 11)
		glyph.add_theme_color_override("font_color", cfg.get("color", Color.WHITE))
		icon_container.add_child(glyph)
	row.add_child(icon_container)
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
	elif label == "Eh":
		bar_frac = clampf((val - EH_MIN_MV) / EH_RANGE_MV, 0.0, 1.0)
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
	elif label == "Eh":
		val_lbl.text = "%.0f" % val
	elif display_val >= 100.0:
		val_lbl.text = "%.0f" % display_val
	elif display_val >= 1.0:
		val_lbl.text = "%.1f" % display_val
	else:
		val_lbl.text = "%.2f" % display_val
	if not unit.is_empty():
		val_lbl.text += " " + unit
	val_lbl.text += suffix
	val_lbl.add_theme_font_size_override("font_size", 9)
	# Color value text by stress zone (same color as bar)
	val_lbl.add_theme_color_override("font_color", bar_color)
	val_lbl.custom_minimum_size.x = 70
	row.add_child(val_lbl)
	row.tooltip_text = cfg.get("tooltip", "")
	parent.add_child(row)


static func _stress_color(key: String, val: float, opt_min: float, opt_max: float) -> Color:
	if key == "pH":
		if val < opt_min - 1.0 or val > opt_max + 1.0:
			return BAR_STRESS
		if val < opt_min or val > opt_max:
			return BAR_MARGINAL
		return BAR_OK
	if key == "Eh":
		if val < EH_ANOXIC_THRESHOLD:
			return BAR_STRESS
		if val < EH_OXIC_THRESHOLD:
			return BAR_MARGINAL
		return BAR_OK
	if key == "MWD":
		if val < 0.5:
			return BAR_STRESS
		if val < 1.5:
			return BAR_MARGINAL
		return BAR_OK
	if val < opt_min * 0.3:
		return BAR_STRESS
	if val < opt_min:
		return BAR_MARGINAL
	return BAR_OK


func _build_biomass_row(parent: VBoxContainer, biomass: Dictionary) -> void:
	## Plant biomass (g/m²) proportion bar (#317).
	## The root portion is only drawn once root biomass is actually reported; the
	## orchestrator currently supplies root_g_m2 == 0 (tracked in #330), so until
	## then we render stem-only rather than ship a visibly-wrong "R 0" split.
	var root_g: float = biomass.get("root_g_m2", 0.0)
	var stem_g: float = biomass.get("stem_g_m2", 0.0)
	var has_root: bool = root_g > 0.0
	var total: float = maxf(root_g + stem_g, 0.001)

	var caption := Label.new()
	caption.text = "PLANT BIOMASS"
	caption.uppercase = true
	caption.add_theme_font_size_override("font_size", 9)
	caption.add_theme_color_override("font_color", UiTheme.TEXT_MUTED)
	caption.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	parent.add_child(caption)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	if has_root:
		row.tooltip_text = (
			"Root vs stem biomass allocation.\n"
			+ "Root: %.0f g/m²  Stem: %.0f g/m²" % [root_g, stem_g]
		)
	else:
		row.tooltip_text = (
			"Stem biomass: %.0f g/m².\n" % stem_g
			+ "Root biomass not yet reported by the engine (#330)."
		)

	var track_w := 120
	var track_h := 12
	var bar_bg := Control.new()
	bar_bg.custom_minimum_size = Vector2(track_w, track_h)
	var track := ColorRect.new()
	track.color = UiTheme.TRACK_BG
	track.size = Vector2(track_w, track_h)
	bar_bg.add_child(track)

	var root_frac: float = clampf(root_g / total, 0.0, 1.0) if has_root else 0.0
	if has_root:
		var root_rect := ColorRect.new()
		root_rect.color = UiTheme.SUBSTANCE_CARBON
		root_rect.position = Vector2(0, 0)
		root_rect.size = Vector2(root_frac * track_w, track_h)
		bar_bg.add_child(root_rect)

	var stem_rect := ColorRect.new()
	stem_rect.color = UiTheme.ACCENT_GREEN
	stem_rect.position = Vector2(root_frac * track_w, 0)
	stem_rect.size = Vector2((1.0 - root_frac) * track_w, track_h)
	bar_bg.add_child(stem_rect)
	row.add_child(bar_bg)

	var lbl := Label.new()
	if has_root:
		lbl.text = "R %.0f / S %.0f g/m²" % [root_g, stem_g]
	else:
		lbl.text = "Stem %.0f g/m²" % stem_g
	lbl.add_theme_font_size_override("font_size", 9)
	lbl.add_theme_color_override("font_color", UiTheme.TEXT_SECONDARY)
	row.add_child(lbl)
	parent.add_child(row)


func _build_cycle_row(parent: VBoxContainer) -> void:
	# Cycle view label
	_cycle_label = Label.new()
	_cycle_label.text = "ALL FLOWS"
	_cycle_label.uppercase = true
	_cycle_label.add_theme_font_size_override("font_size", 9)
	_cycle_label.add_theme_color_override("font_color", UiTheme.TEXT_MUTED)
	_cycle_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	parent.add_child(_cycle_label)
	# Button row
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 2)
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	parent.add_child(row)
	var colors := {
		"all": UiTheme.TEXT_PRIMARY,
		"water": UiTheme.SUBSTANCE_WATER,
		"nitrogen": UiTheme.SUBSTANCE_NO3,
		"carbon": UiTheme.SUBSTANCE_CARBON,
		"phosphorus": UiTheme.SUBSTANCE_PHOSPHORUS,
	}
	var labels := {
		"all": "All",
		"water": "H\u2082O",
		"nitrogen": "N",
		"carbon": "C",
		"phosphorus": "P",
	}
	_filter_buttons.clear()
	for fkey: String in FlowOverlay.CYCLE_FILTERS:
		var btn := Button.new()
		btn.text = labels.get(fkey, fkey)
		btn.custom_minimum_size = Vector2(36, 22)
		UiTheme.style_button(btn)
		btn.add_theme_font_size_override("font_size", 10)
		var col: Color = colors.get(fkey, UiTheme.TEXT_PRIMARY)
		btn.add_theme_color_override("font_color", col)
		btn.add_theme_color_override("font_hover_color", col.lightened(0.3))
		btn.pressed.connect(_on_filter_btn.bind(fkey))
		_filter_buttons[fkey] = btn
		row.add_child(btn)
	_update_button_highlight()
	# Toggle visibility
	var toggle := Button.new()
	toggle.text = "EYE"
	toggle.tooltip_text = "Toggle flow overlay"
	toggle.custom_minimum_size = Vector2(36, 22)
	UiTheme.style_button(toggle)
	toggle.add_theme_font_size_override("font_size", 9)
	toggle.pressed.connect(_on_toggle_btn)
	row.add_child(toggle)


func _on_filter_btn(filter_name: String) -> void:
	_active_filter = filter_name
	_update_button_highlight()
	if _cycle_label:
		_cycle_label.text = FlowOverlay.CYCLE_LABELS.get(filter_name, "ALL FLOWS")
	if not _flow_visible:
		_flow_visible = true
		flow_toggle_changed.emit(true)
	flow_filter_changed.emit(filter_name)


func _on_toggle_btn() -> void:
	_flow_visible = not _flow_visible
	flow_toggle_changed.emit(_flow_visible)


func _update_button_highlight() -> void:
	for fkey: String in _filter_buttons:
		var btn: Button = _filter_buttons[fkey]
		if fkey == _active_filter:
			btn.add_theme_stylebox_override("normal", UiTheme.create_button_style("hover"))
		else:
			btn.add_theme_stylebox_override("normal", UiTheme.create_button_style("normal"))


static func _format_acceptor(acc: String) -> String:
	## Format acceptor with subscript unicode.
	match acc:
		"O2":
			return "O\u2082"
		"NO3":
			return "NO\u2083\u207b"
		"Fe3+":
			return "Fe\u00b3\u207a"
		"CH4":
			return "CH\u2084"
		_:
			return acc
