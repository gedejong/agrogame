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
