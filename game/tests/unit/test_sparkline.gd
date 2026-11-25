extends GutTest

const SparklineScript = preload("res://scripts/sparkline.gd")


func test_empty_data() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Test", "", Color.WHITE)
	spark.set_data(PackedFloat64Array())
	assert_eq(spark.get_latest_value(), 0.0, "Empty = 0")
	spark.free()


func test_single_point() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Test", "", Color.WHITE)
	spark.set_data(PackedFloat64Array([5.0]))
	assert_eq(spark.get_latest_value(), 5.0, "Single = 5")
	spark.free()


func test_auto_scaling() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Test", "", Color.WHITE)
	spark.set_data(PackedFloat64Array([0.0, 10.0, 5.0]))
	# Y range should encompass 0-10 with padding
	assert_lt(spark._y_min, 0.0, "Min padded below 0")
	assert_gt(spark._y_max, 10.0, "Max padded above 10")
	spark.free()


func test_latest_value() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Test", "", Color.WHITE)
	spark.set_data(PackedFloat64Array([1.0, 2.0, 3.0, 4.0]))
	assert_eq(spark.get_latest_value(), 4.0, "Latest = last element")
	spark.free()


func test_color_parameter() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("LAI", "m²/m²", Color.GREEN)
	assert_eq(spark._color, Color.GREEN, "Color matches setup")
	spark.free()


func test_stage_days_stored() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Test", "", Color.WHITE)
	var stages := PackedInt32Array([5, 10])
	spark.set_data(
		PackedFloat64Array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]), stages
	)
	assert_eq(spark._stage_days.size(), 2, "Stage days stored")
	assert_eq(spark._stage_days[0], 5)
	spark.free()


func test_value_text_formats() -> void:
	# A gauge prints the card's integer (QuickStatusCard floors score + 1e-6).
	assert_eq(SparklineScript.value_text(46.0, "", true), "46")
	assert_eq(SparklineScript.value_text(21.6, "", true), "21")
	assert_eq(SparklineScript.value_text(0.9999999999999998 * 100.0, "", true), "100")
	# Other series keep 0, 1 or 2 decimals by magnitude, then the unit.
	assert_eq(SparklineScript.value_text(0.05, "m³/m³", false), "0.05 m³/m³")
	assert_eq(SparklineScript.value_text(2.345, "", false), "2.3")
	assert_eq(SparklineScript.value_text(123.4, "mV", false), "123 mV")


func test_gauge_series_has_a_fixed_0_to_100_range() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Water", "", Color.WHITE, 36.0, true)
	spark.set_data(PackedFloat64Array([100.0, 95.0]))
	assert_eq([spark._y_min, spark._y_max], [0.0, 100.0])
	assert_eq(spark.label_text(), "Water: 95")
	spark.free()


func test_label_text_dash_when_the_value_does_not_apply() -> void:
	var spark := Control.new()
	spark.set_script(SparklineScript)
	spark.setup("Water", "", Color.WHITE, 36.0, true)
	spark.set_data(PackedFloat64Array([40.0, 100.0]), PackedInt32Array(), false)
	assert_eq(spark.label_text(), "Water: —")
	spark.set_data(PackedFloat64Array())
	assert_eq(spark.label_text(), "Water: ", "no data, no value")
	spark.free()
