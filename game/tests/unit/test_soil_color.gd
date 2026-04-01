extends GutTest
## Tests for soil color calculation logic (AGRO-119).

const SoilColor = preload("res://scripts/soil_color.gd")


func test_no_som_no_moisture_returns_white() -> void:
	var color := SoilColor.calculate(0.0, 0.0)
	assert_eq(color, Color.WHITE, "No SOM + no moisture = no modulation")


func test_high_som_darkens_tile() -> void:
	var low_som := SoilColor.calculate(200.0, 0.0)
	var high_som := SoilColor.calculate(5000.0, 0.0)
	assert_true(
		high_som.v < low_som.v,
		"High SOM should be darker (lower value) than low SOM",
	)


func test_high_moisture_darkens_tile() -> void:
	var dry := SoilColor.calculate(2000.0, 0.05)
	var wet := SoilColor.calculate(2000.0, 0.40)
	assert_true(
		wet.v < dry.v,
		"Wet soil should be darker than dry soil",
	)


func test_som_and_moisture_stack() -> void:
	var som_only := SoilColor.calculate(4000.0, 0.0)
	var moisture_only := SoilColor.calculate(0.0, 0.40)
	var both := SoilColor.calculate(4000.0, 0.40)
	assert_true(
		both.v < som_only.v,
		"SOM + moisture combined should be darker than SOM alone",
	)
	assert_true(
		both.v < moisture_only.v,
		"SOM + moisture combined should be darker than moisture alone",
	)


func test_color_stays_in_valid_range() -> void:
	# Extreme values should not exceed valid color range
	var extreme := SoilColor.calculate(10000.0, 1.0)
	assert_true(extreme.r >= 0.0 and extreme.r <= 1.0, "R in range")
	assert_true(extreme.g >= 0.0 and extreme.g <= 1.0, "G in range")
	assert_true(extreme.b >= 0.0 and extreme.b <= 1.0, "B in range")


func test_transitions_smooth() -> void:
	# Verify no discontinuities: stepping SOM by small increments
	var prev := SoilColor.calculate(0.0, 0.2)
	for step in range(1, 10):
		var som: float = step * 500.0
		var current := SoilColor.calculate(som, 0.2)
		var diff: float = abs(current.v - prev.v)
		assert_true(
			diff < 0.15,
			"Color step should be smooth (diff=%.3f at SOM=%.0f)" % [diff, som],
		)
		prev = current


func test_degraded_vs_rich_visible_difference() -> void:
	## AC: SOM < 1% (~500 g C/m²) should look noticeably paler than SOM > 3% (~3000 g C/m²)
	var degraded := SoilColor.calculate(400.0, 0.15)
	var rich := SoilColor.calculate(3000.0, 0.15)
	var lightness_diff: float = degraded.v - rich.v
	assert_true(
		lightness_diff > 0.05,
		"Degraded should be noticeably lighter than rich (diff=%.3f)" % lightness_diff,
	)
