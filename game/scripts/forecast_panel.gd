extends VBoxContainer
## 5-day weather forecast panel showing temperature and rain.

var _days: Array = []


func update_forecast(forecast_data: Array) -> void:
	_days = forecast_data
	_rebuild_display()


func _rebuild_display() -> void:
	for child in get_children():
		child.queue_free()

	var header := Label.new()
	header.text = "5-Day Forecast"
	header.add_theme_font_size_override("font_size", 13)
	add_child(header)

	for day: Dictionary in _days:
		var label := Label.new()
		var rain: float = day.get("rain_mm", 0.0)
		var rain_icon := "☀" if rain < 1.0 else ("🌧" if rain > 5.0 else "⛅")
		label.text = (
			"%s %s %.0f–%.0f°C  %.1fmm"
			% [
				str(day.get("date", "")).substr(5),
				rain_icon,
				day.get("tmin_c", 0.0),
				day.get("tmax_c", 0.0),
				rain,
			]
		)
		label.add_theme_font_size_override("font_size", 11)
		add_child(label)
