extends GutTest

const DC = preload("res://scripts/debug_console.gd")


func test_sliders_defined() -> void:
	assert_eq(DC.SLIDERS.size(), 3, "3 debug sliders")
	assert_true(DC.SLIDERS.has("wind_ms"), "Has wind_ms")
	assert_true(DC.SLIDERS.has("wind_angle"), "Has wind_angle")
	assert_true(DC.SLIDERS.has("rain_mm"), "Has rain_mm")


func test_toggle_visibility() -> void:
	var console := DC.new()
	add_child_autofree(console)
	assert_false(console.visible, "Starts hidden")
	console.toggle()
	assert_true(console.visible, "Toggled on")
	console.toggle()
	assert_false(console.visible, "Toggled off")
