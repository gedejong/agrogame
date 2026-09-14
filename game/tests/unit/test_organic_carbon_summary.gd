extends GutTest

const Summary = preload("res://scripts/organic_carbon_summary.gd")
const MASS_SETTING := "agrogame/display/mass_unit"

var _previous_unit: Variant


func before_each() -> void:
	_previous_unit = ProjectSettings.get_setting(MASS_SETTING)
	ProjectSettings.set_setting(MASS_SETTING, UiTheme.MASS_UNIT_GM2)


func after_each() -> void:
	ProjectSettings.set_setting(MASS_SETTING, _previous_unit)


func _make_summary(pools: Dictionary) -> VBoxContainer:
	var summary := VBoxContainer.new()
	summary.set_script(Summary)
	add_child_autofree(summary)
	summary.show_pools(pools)
	return summary


func test_total_is_sum_of_all_three_pools() -> void:
	var summary := _make_summary({"Labile": 100.0, "Intermediate": 200.0, "Stable": 700.0})
	assert_eq(summary.get_node("TotalRow/TotalCarbonValue").text, "100.0 gC/m²")
	assert_eq(summary.get_node("PoolBreakdown/Labile/Value").text, "10.0 gC/m²")
	assert_eq(summary.get_node("PoolBreakdown/Intermediate/Value").text, "20.0 gC/m²")
	assert_eq(summary.get_node("PoolBreakdown/Stable/Value").text, "70.0 gC/m²")


func test_pool_reallocation_preserves_total_and_neutral_status() -> void:
	var summary := _make_summary({"Labile": 100.0, "Intermediate": 200.0, "Stable": 700.0})
	var previous_text: String = summary.get_node("TotalRow/TotalCarbonValue").text
	summary.show_pools({"Labile": 10.0, "Intermediate": 200.0, "Stable": 790.0})
	assert_eq(summary.get_node("TotalRow/TotalCarbonValue").text, previous_text)
	assert_eq(
		summary.get_node("TotalRow/TotalCarbonValue").get_theme_color("font_color"),
		UiTheme.TEXT_PRIMARY,
		"A small labile stock must not imply deficient total carbon"
	)


func test_carbon_units_preserve_native_kg_ha() -> void:
	ProjectSettings.set_setting(MASS_SETTING, UiTheme.MASS_UNIT_KGHA)
	var summary := _make_summary({"Labile": 100.0, "Intermediate": 200.0, "Stable": 700.0})
	assert_eq(summary.get_node("TotalRow/TotalCarbonValue").text, "1000.0 kgC/ha")
	assert_eq(summary.get_node("PoolBreakdown/Labile/Value").text, "100.0 kgC/ha")


func test_breakdown_is_collapsed_and_keyboard_focusable() -> void:
	var summary := _make_summary({"Labile": 0.0, "Intermediate": 0.0, "Stable": 0.0})
	var toggle: Button = summary.get_node("TotalRow/TogglePools")
	assert_false(summary.get_node("PoolBreakdown").visible)
	assert_eq(toggle.focus_mode, Control.FOCUS_ALL)
	toggle.button_pressed = true
	assert_true(summary.get_node("PoolBreakdown").visible)
	assert_eq(toggle.text, "▾")
	toggle.button_pressed = false
	assert_false(summary.get_node("PoolBreakdown").visible)
	assert_eq(summary.get_node("TotalRow/TotalCarbonValue").text, "0.0 gC/m²")


func test_missing_pool_does_not_fabricate_total_or_zero() -> void:
	var summary := _make_summary({"Labile": 100.0, "Intermediate": 200.0})
	assert_eq(summary.get_node("TotalRow/TotalCarbonValue").text, "Unavailable")
	assert_eq(summary.get_node("PoolBreakdown/Stable/Value").text, "Unavailable")
	assert_eq(summary.get_node("PoolBreakdown/Labile/Value").text, "10.0 gC/m²")


func test_layer_selection_and_partial_arrays() -> void:
	var soil := {
		"som_labile_c": [10.0, 20.0],
		"som_intermediate_c": [100.0, 200.0],
		"som_stable_c": [1000.0],
	}
	assert_eq(
		Summary.pools_for_layer(soil, 0), {"Labile": 10.0, "Intermediate": 100.0, "Stable": 1000.0}
	)
	assert_eq(Summary.pools_for_layer(soil, 1), {"Labile": 20.0, "Intermediate": 200.0})
	assert_eq(Summary.pools_for_layer(soil, -1), {})
	assert_eq(Summary.pools_for_layer(soil, 2), {})
	assert_eq(Summary.pools_for_layer({}, 0), {})


func test_invalid_carbon_is_unavailable() -> void:
	for invalid: Variant in [null, "100", -1.0, NAN, INF]:
		var soil := {"som_labile_c": [invalid], "som_intermediate_c": null}
		assert_eq(Summary.pools_for_layer(soil, 0), {})
		var summary := _make_summary({"Labile": invalid, "Intermediate": 1.0, "Stable": 2.0})
		assert_eq(summary.get_node("TotalRow/TotalCarbonValue").text, "Unavailable")
		assert_eq(summary.get_node("PoolBreakdown/Labile/Value").text, "Unavailable")


func test_composition_track_shows_pool_shares_not_stock_health() -> void:
	var summary := _make_summary({"Labile": 100.0, "Intermediate": 200.0, "Stable": 700.0})
	var track: Control = summary.get_node("TotalRow/CompositionTrack")
	assert_eq(track.custom_minimum_size, Vector2(100, 12))
	assert_almost_eq(track.get_node("Labile").size.x, 10.0, 0.001)
	assert_almost_eq(track.get_node("Intermediate").size.x, 20.0, 0.001)
	assert_almost_eq(track.get_node("Stable").size.x, 70.0, 0.001)
	assert_almost_eq(track.get_node("Stable").position.x, 30.0, 0.001)
	assert_eq(track.get_node("Labile").color, UiTheme.SUBSTANCE_CARBON)


func test_composition_track_is_empty_for_zero_or_missing_stock() -> void:
	for pools: Dictionary in [{}, {"Labile": 0.0, "Intermediate": 0.0, "Stable": 0.0}]:
		var summary := _make_summary(pools)
		var track: Control = summary.get_node("TotalRow/CompositionTrack")
		assert_false(track.has_node("Labile"))
		assert_false(track.has_node("Intermediate"))
		assert_false(track.has_node("Stable"))
