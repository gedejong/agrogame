extends PanelContainer
## Tile info popup: tabbed sparkline history.
## 4 tabs (Crop/Water/Nutrients/Soil) with 2-3 sparklines each.
## Ref: Shneiderman 1996 — progressive disclosure.

const Sparkline = preload("res://scripts/sparkline.gd")

## Graph configs organized by tab. Max 4 per tab.
const TABS := {
	"Crop":
	[
		{
			"key": "lai",
			"label": "LAI",
			"unit": "m²/m²",
			"mass_type": "",
			"color": UiTheme.ACCENT_GREEN
		},
		{
			"key": "grain_g_m2",
			"label": "Grain",
			"unit": "",
			"mass_type": "mass",
			"color": UiTheme.ACCENT_GOLD
		},
		{
			"key": "root_depth_cm",
			"label": "Root depth",
			"unit": "cm",
			"mass_type": "",
			"color": Color(0.55, 0.40, 0.25)
		},
	],
	# The Quick Status Water and Root zone gauges over time (#669): "gauge"
	# prints the card's integer on 0-100; "standing_only" prints "—" when the
	# latest day's crop does not stand, as the card does.
	"Water":
	[
		{
			"key": "water",
			"label": "Water",
			"unit": "",
			"mass_type": "",
			"color": UiTheme.SUBSTANCE_WATER,
			"gauge": true,
			"standing_only": true,
		},
		{
			"key": "root_zone",
			"label": "Root zone",
			"unit": "",
			"mass_type": "",
			"color": Color(0.55, 0.40, 0.25),
			"gauge": true,
		},
		{
			"key": "theta_surface",
			"label": "Topsoil water",
			"unit": "m³/m³",
			"mass_type": "",
			"color": UiTheme.TEXT_SECONDARY
		},
	],
	"Nutrients":
	[
		{
			"key": "n_available",
			"label": "N available",
			"unit": "",
			"mass_type": "mass",
			"color": UiTheme.SUBSTANCE_NO3
		},
		{
			"key": "fe_available_surface",
			"label": "Fe avail",
			"unit": "ppm",
			"mass_type": "",
			"color": Color(0.75, 0.45, 0.20)
		},
		{
			"key": "zn_available_surface",
			"label": "Zn avail",
			"unit": "ppm",
			"mass_type": "",
			"color": Color(0.45, 0.55, 0.70)
		},
		{
			"key": "mn_available_surface",
			"label": "Mn avail",
			"unit": "ppm",
			"mass_type": "",
			"color": Color(0.50, 0.35, 0.60)
		},
	],
	"Soil":
	[
		{
			"key": "agg_mwd_surface",
			"label": "MWD",
			"unit": "mm",
			"mass_type": "",
			"color": UiTheme.SUBSTANCE_AGGREGATE
		},
		{
			"key": "redox_eh_surface",
			"label": "Redox Eh",
			"unit": "mV",
			"mass_type": "",
			"color": UiTheme.SUBSTANCE_REDOX
		},
	],
}

## Flat key-existence lookup (for tests). Full config is in TABS.
const GRAPHS := {
	"lai": {"label": "LAI"},
	"grain_g_m2": {"label": "Grain"},
	"root_depth_cm": {"label": "Root depth"},
	"water": {"label": "Water"},
	"root_zone": {"label": "Root zone"},
	"theta_surface": {"label": "Topsoil water"},
	"n_available": {"label": "N available"},
	"fe_available_surface": {"label": "Fe avail"},
	"zn_available_surface": {"label": "Zn avail"},
	"mn_available_surface": {"label": "Mn avail"},
	"agg_mwd_surface": {"label": "MWD"},
	"redox_eh_surface": {"label": "Redox Eh"},
}

var _sparklines: Dictionary = {}
var _tab_container: TabContainer = null
var _last_tab: int = 0


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

	# Day count
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

	var stage_days := _find_stage_transitions(history)

	# Tabbed sparklines
	_tab_container = TabContainer.new()
	_tab_container.custom_minimum_size = Vector2(220, 0)
	_tab_container.add_theme_font_size_override("font_size", 10)
	_sparklines.clear()

	for tab_name: String in TABS:
		var tab_vbox := VBoxContainer.new()
		tab_vbox.name = tab_name
		tab_vbox.add_theme_constant_override("separation", 2)
		for cfg: Dictionary in TABS[tab_name]:
			var spark := Control.new()
			spark.set_script(Sparkline)
			var display_unit: String = cfg.get("unit", "")
			if cfg.get("mass_type", "") == "mass":
				display_unit = UiTheme.mass_label()
			spark.setup(cfg["label"], display_unit, cfg["color"], 36.0, cfg.get("gauge", false))
			var data := _extract_series(history, cfg["key"])
			spark.set_data(data, stage_days, _value_shown(history, cfg))
			_sparklines[cfg["key"]] = spark
			tab_vbox.add_child(spark)
		_tab_container.add_child(tab_vbox)

	# Restore last selected tab
	_tab_container.current_tab = clampi(_last_tab, 0, _tab_container.get_tab_count() - 1)
	_tab_container.tab_changed.connect(_on_tab_changed)
	vbox.add_child(_tab_container)
	visible = true


func update_history(history: Array) -> void:
	if _sparklines.is_empty():
		return
	var stage_days := _find_stage_transitions(history)
	for tab_name: String in TABS:
		for cfg: Dictionary in TABS[tab_name]:
			var key: String = cfg["key"]
			if _sparklines.has(key):
				var data := _extract_series(history, key)
				_sparklines[key].set_data(data, stage_days, _value_shown(history, cfg))


func hide_panel() -> void:
	_clear()
	visible = false


func _on_tab_changed(tab: int) -> void:
	_last_tab = tab


func _clear() -> void:
	_sparklines.clear()
	_tab_container = null
	for child in get_children():
		remove_child(child)
		child.queue_free()


## False for a standing-only series once the latest day's crop does not stand.
static func _value_shown(history: Array, cfg: Dictionary) -> bool:
	if not cfg.get("standing_only", false) or history.is_empty():
		return true
	return String(history[-1].get("crop_stage", "")) in QuickStatusCard.STANDING_STAGES


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
