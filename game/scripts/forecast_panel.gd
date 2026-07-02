extends VBoxContainer
## 5-day forecast panel: weather plus projected water-stress and mineral-N
## decision-support trend lines (#318).

const ICON_SIZE := 16
const ICON_SUN := "res://assets/icons/icon_sun.svg"
const ICON_CLOUD := "res://assets/icons/icon_cloud.svg"
const ICON_RAIN := "res://assets/icons/icon_rain.svg"

## Ks below this projected value flags a water-stress risk (amber/red text).
const WATER_STRESS_WARN := 0.6
## Projected mineral N (kg/ha) below this flags an N-shortfall risk.
const MINERAL_N_WARN_KG_HA := 30.0

var _days: Array = []


func update_forecast(forecast_data: Array) -> void:
	_days = forecast_data
	_rebuild_display()


func _rebuild_display() -> void:
	for child in get_children():
		child.queue_free()

	var bg := PanelContainer.new()
	var bg_style := UiTheme.create_panel_style(true)
	bg_style.content_margin_left = 5
	bg_style.content_margin_right = 5
	bg_style.content_margin_top = 5
	bg_style.content_margin_bottom = 5
	bg.add_theme_stylebox_override("panel", bg_style)
	UiTheme.add_blur_bg(bg)

	var content := VBoxContainer.new()
	bg.add_child(content)
	add_child(bg)

	var header := Label.new()
	header.text = "5-Day Outlook"
	header.uppercase = true
	header.add_theme_font_size_override("font_size", 12)
	header.add_theme_color_override("font_color", UiTheme.HEADER_COLOR)
	content.add_child(header)

	for day: Dictionary in _days:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 4)

		# Weather icon
		var icon := TextureRect.new()
		var rain: float = day.get("rain_mm", 0.0)
		var icon_path := ICON_SUN
		if rain > 5.0:
			icon_path = ICON_RAIN
		elif rain >= 1.0:
			icon_path = ICON_CLOUD
		var tex: Texture2D = load(icon_path)
		if tex:
			icon.texture = tex
		icon.custom_minimum_size = Vector2(ICON_SIZE, ICON_SIZE)
		icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		icon.modulate = UiTheme.ICON_TINT
		row.add_child(icon)

		# Weather text
		var label := Label.new()
		label.text = (
			"%s %.0f\u2013%.0f\u00b0C %.1fmm"
			% [
				str(day.get("date", "")).substr(5),
				day.get("tmin_c", 0.0),
				day.get("tmax_c", 0.0),
				rain,
			]
		)
		label.add_theme_font_size_override("font_size", 10)
		label.add_theme_color_override("font_color", UiTheme.BODY_COLOR)
		row.add_child(label)

		# Soil/crop projection: water-stress + mineral-N trend (#318)
		var soil := Label.new()
		var water_stress: float = day.get("water_stress", 1.0)
		var mineral_n: float = day.get("mineral_n_kg_ha", 0.0)
		soil.text = "\u2022 W%.0f%% N%.0f" % [water_stress * 100.0, mineral_n]
		soil.add_theme_font_size_override("font_size", 10)
		soil.add_theme_color_override("font_color", _projection_color(water_stress, mineral_n))
		row.add_child(soil)

		content.add_child(row)


func _projection_color(water_stress: float, mineral_n: float) -> Color:
	## Amber/red when the projection crosses a water- or N-shortfall threshold.
	if water_stress < WATER_STRESS_WARN or mineral_n < MINERAL_N_WARN_KG_HA:
		return UiTheme.ACCENT_RED
	return UiTheme.ACCENT_GREEN
