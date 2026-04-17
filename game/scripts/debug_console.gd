class_name DebugConsole
extends PanelContainer
## In-game debug console for tweaking parameters at runtime.
## Toggle with backtick (`) key. Sliders update values live.

signal wind_changed(strength: float, direction: Vector2)
signal rain_changed(raining: bool, intensity: float)

const SLIDERS := {
	"wind_ms": {"label": "Wind m/s", "min": 0.0, "max": 15.0, "default": 2.0},
	"wind_angle": {"label": "Wind dir °", "min": 0.0, "max": 360.0, "default": 45.0},
	"rain_mm": {"label": "Rain mm", "min": 0.0, "max": 30.0, "default": 0.0},
}

var _slider_refs: Dictionary = {}
var _info_label: Label = null


func _ready() -> void:
	visible = false
	_build_ui()


func _build_ui() -> void:
	var style := UiTheme.create_panel_style()
	add_theme_stylebox_override("panel", style)
	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 4)
	add_child(vbox)
	var title := Label.new()
	title.text = "DEBUG CONSOLE (`)"
	title.add_theme_font_size_override("font_size", 11)
	title.add_theme_color_override("font_color", UiTheme.ACCENT_GOLD)
	vbox.add_child(title)
	for key: String in SLIDERS:
		var def: Dictionary = SLIDERS[key]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 4)
		var lbl := Label.new()
		lbl.text = def["label"]
		lbl.add_theme_font_size_override("font_size", 10)
		lbl.custom_minimum_size.x = 70
		row.add_child(lbl)
		var slider := HSlider.new()
		slider.min_value = def["min"]
		slider.max_value = def["max"]
		slider.step = 0.1
		slider.value = def["default"]
		slider.custom_minimum_size.x = 120
		slider.value_changed.connect(_on_slider_changed)
		row.add_child(slider)
		var val_lbl := Label.new()
		val_lbl.text = "%.1f" % def["default"]
		val_lbl.add_theme_font_size_override("font_size", 10)
		val_lbl.custom_minimum_size.x = 35
		row.add_child(val_lbl)
		_slider_refs[key] = {"slider": slider, "label": val_lbl}
		vbox.add_child(row)
	_info_label = Label.new()
	_info_label.add_theme_font_size_override("font_size", 9)
	_info_label.add_theme_color_override("font_color", UiTheme.TEXT_MUTED)
	vbox.add_child(_info_label)


func _on_slider_changed(_value: float) -> void:
	for key: String in _slider_refs:
		var s: Dictionary = _slider_refs[key]
		s["label"].text = "%.1f" % s["slider"].value
	var wind_ms: float = _slider_refs["wind_ms"]["slider"].value
	var angle_deg: float = _slider_refs["wind_angle"]["slider"].value
	var angle_rad: float = deg_to_rad(angle_deg)
	var wind_dir := Vector2(cos(angle_rad), sin(angle_rad))
	var strength: float = clampf(wind_ms / 8.0, 0.05, 1.0)
	wind_changed.emit(strength, wind_dir)
	var rain_mm: float = _slider_refs["rain_mm"]["slider"].value
	rain_changed.emit(rain_mm > 1.0, rain_mm)
	_info_label.text = "str=%.2f dir=(%.1f,%.1f)" % [strength, wind_dir.x, wind_dir.y]


func toggle() -> void:
	visible = not visible
