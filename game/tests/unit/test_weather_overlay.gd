extends GutTest
## Tests for weather overlay (rain particles).

const WeatherScript = preload("res://scripts/weather_overlay.gd")


func test_instantiation() -> void:
	var w = WeatherScript.new()
	assert_not_null(w, "WeatherOverlay should instantiate")
	w.free()
