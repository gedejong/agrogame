extends RefCounted
## Crop info panel — displays LAI, root depth, grain, and stress as a floating overlay.

const _STRESS_NONE := 0
const _STRESS_WILTING := 1
const _STRESS_N_DEFICIENT := 2


static func create(data: Dictionary) -> PanelContainer:
	var crop_key: String = data.get("crop_key", "")
	var stage_name: String = data.get("crop_stage_name", "")
	if crop_key.is_empty() and stage_name.is_empty():
		return null

	var panel := PanelContainer.new()
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.1, 0.1, 0.12, 0.9)
	style.corner_radius_top_left = 4
	style.corner_radius_top_right = 4
	style.corner_radius_bottom_left = 4
	style.corner_radius_bottom_right = 4
	style.border_width_left = 1
	style.border_width_right = 1
	style.border_width_top = 1
	style.border_width_bottom = 1
	style.border_color = Color(0.4, 0.4, 0.45, 0.5)
	style.content_margin_left = 8
	style.content_margin_right = 8
	style.content_margin_top = 6
	style.content_margin_bottom = 6
	panel.add_theme_stylebox_override("panel", style)

	var vbox := VBoxContainer.new()
	vbox.add_theme_constant_override("separation", 2)
	panel.add_child(vbox)

	var title := Label.new()
	title.text = "%s — %s" % [crop_key.capitalize(), stage_name]
	title.add_theme_font_size_override("font_size", 13)
	title.add_theme_color_override("font_color", Color(0.9, 0.9, 0.95))
	vbox.add_child(title)

	var lai: float = data.get("lai", 0.0)
	var root_cm: float = data.get("root_depth_cm", 0.0)
	var grain: float = data.get("grain_g_m2", 0.0)
	var stress: int = data.get("stress", 0)

	_add_stat(vbox, "LAI", "%.2f m²/m²" % lai, clampf(lai / 6.0, 0, 1), Color(0.3, 0.8, 0.3))
	_add_stat(
		vbox, "Root", "%.0f cm" % root_cm, clampf(root_cm / 100.0, 0, 1), Color(0.6, 0.45, 0.25)
	)
	_add_stat(
		vbox, "Grain", "%.0f g/m²" % grain, clampf(grain / 1000.0, 0, 1), Color(0.85, 0.75, 0.2)
	)

	if stress != _STRESS_NONE:
		var stress_label := Label.new()
		var stress_name := "Wilting" if stress == _STRESS_WILTING else "N Deficient"
		stress_label.text = "⚠ %s" % stress_name
		stress_label.add_theme_font_size_override("font_size", 11)
		stress_label.add_theme_color_override("font_color", Color(0.9, 0.3, 0.3))
		vbox.add_child(stress_label)

	return panel


static func _add_stat(
	parent: VBoxContainer, label_text: String, value_text: String, frac: float, color: Color
) -> void:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)

	var lbl := Label.new()
	lbl.text = label_text
	lbl.add_theme_font_size_override("font_size", 10)
	lbl.add_theme_color_override("font_color", Color(0.7, 0.7, 0.75))
	lbl.custom_minimum_size.x = 35
	row.add_child(lbl)

	var bar_bg := ColorRect.new()
	bar_bg.color = Color(0.2, 0.2, 0.25, 0.5)
	bar_bg.custom_minimum_size = Vector2(60, 8)
	var bar_fill := ColorRect.new()
	bar_fill.color = color
	bar_fill.size = Vector2(60 * frac, 8)
	bar_bg.add_child(bar_fill)
	row.add_child(bar_bg)

	var val := Label.new()
	val.text = value_text
	val.add_theme_font_size_override("font_size", 10)
	val.add_theme_color_override("font_color", Color(0.85, 0.85, 0.9))
	row.add_child(val)

	parent.add_child(row)
