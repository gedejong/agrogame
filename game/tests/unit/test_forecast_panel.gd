extends GutTest
## Tests for the forecast panel display logic.

const ForecastPanel = preload("res://scripts/forecast_panel.gd")


func test_update_forecast_creates_labels() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)

	var forecast := [
		{"date": "2024-04-02", "tmin_c": 5.0, "tmax_c": 15.0, "rain_mm": 0.0},
		{"date": "2024-04-03", "tmin_c": 6.0, "tmax_c": 18.0, "rain_mm": 8.0},
	]
	panel.update_forecast(forecast)

	# Header + 2 day labels = 3 children
	assert_eq(panel.get_child_count(), 3, "Should have header + 2 day labels")


func test_empty_forecast_shows_header_only() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)

	panel.update_forecast([])
	assert_eq(panel.get_child_count(), 1, "Empty forecast = header only")
