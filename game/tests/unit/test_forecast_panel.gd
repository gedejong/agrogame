extends GutTest
## Tests for the forecast panel with SVG icons.

const ForecastPanel = preload("res://scripts/forecast_panel.gd")


func test_update_forecast_creates_panel_with_rows() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)

	var forecast := [
		{"date": "2024-04-02", "tmin_c": 5.0, "tmax_c": 15.0, "rain_mm": 0.0},
		{"date": "2024-04-03", "tmin_c": 6.0, "tmax_c": 18.0, "rain_mm": 8.0},
	]
	panel.update_forecast(forecast)

	# Should have 1 PanelContainer child (the background wrapper)
	assert_eq(panel.get_child_count(), 1, "Should have 1 panel container")


func test_empty_forecast_shows_header_only() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)

	panel.update_forecast([])
	assert_eq(panel.get_child_count(), 1, "Empty forecast = panel with header only")


func test_forecast_with_soil_projection_builds_rows() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)

	var forecast := [
		{
			"date": "2024-04-02",
			"tmin_c": 5.0,
			"tmax_c": 15.0,
			"rain_mm": 0.0,
			"water_stress": 0.9,
			"mineral_n_kg_ha": 80.0,
		},
		{
			"date": "2024-04-03",
			"tmin_c": 6.0,
			"tmax_c": 18.0,
			"rain_mm": 8.0,
			"water_stress": 0.3,
			"mineral_n_kg_ha": 12.0,
		},
	]
	panel.update_forecast(forecast)
	assert_eq(panel.get_child_count(), 1, "Should have 1 panel container")


func test_projection_color_flags_water_stress_risk() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)
	# Low Ks (below WATER_STRESS_WARN) but ample N -> risk color (red).
	var risk: Color = panel._projection_color(0.3, 100.0)
	assert_eq(risk, UiTheme.ACCENT_RED, "Low water-stress projection flags red")


func test_projection_color_flags_low_nitrogen_risk() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)
	# Ample water but N below MINERAL_N_WARN_KG_HA -> risk color (red).
	var risk: Color = panel._projection_color(1.0, 10.0)
	assert_eq(risk, UiTheme.ACCENT_RED, "Low mineral-N projection flags red")


func test_projection_color_healthy_is_green() -> void:
	var panel := VBoxContainer.new()
	panel.set_script(ForecastPanel)
	add_child_autofree(panel)
	var ok: Color = panel._projection_color(1.0, 100.0)
	assert_eq(ok, UiTheme.ACCENT_GREEN, "Healthy projection is green")


func test_icon_paths_valid() -> void:
	# Verify SVG icon files exist (load() returns null in headless CI)
	assert_true(
		FileAccess.file_exists(ForecastPanel.ICON_SUN),
		"Sun icon file should exist",
	)
	assert_true(
		FileAccess.file_exists(ForecastPanel.ICON_CLOUD),
		"Cloud icon file should exist",
	)
	assert_true(
		FileAccess.file_exists(ForecastPanel.ICON_RAIN),
		"Rain icon file should exist",
	)
