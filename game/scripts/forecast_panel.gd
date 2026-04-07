extends VBoxContainer
## 5-day weather forecast panel with SVG weather icons.

const ICON_SIZE := 16
const ICON_SUN := "res://assets/icons/icon_sun.svg"
const ICON_CLOUD := "res://assets/icons/icon_cloud.svg"
const ICON_RAIN := "res://assets/icons/icon_rain.svg"

var _days: Array = []


func update_forecast(forecast_data: Array) -> void:
	_days = forecast_data
	_rebuild_display()


func _rebuild_display() -> void:
	for child in get_children():
		child.queue_free()

	var bg := PanelContainer.new()
	bg.add_theme_stylebox_override("panel", UiTheme.create_panel_style())
	UiTheme.add_blur_bg(bg)

	var content := VBoxContainer.new()
	bg.add_child(content)
	add_child(bg)

	var header := Label.new()
	header.text = "5-DAY FORECAST"
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

		# Text
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

		content.add_child(row)
