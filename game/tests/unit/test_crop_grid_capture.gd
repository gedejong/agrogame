extends GutTest

const GridCapture = preload("res://scripts/crop_grid_capture.gd")


func test_crops_and_cols_defined() -> void:
	assert_eq(GridCapture.CROPS.size(), 5, "5 crop types")
	assert_eq(GridCapture.COLS.size(), 6, "6 growth columns")


func test_cols_have_required_keys() -> void:
	for col: Dictionary in GridCapture.COLS:
		assert_true(col.has("label"), "Column has label")
		assert_true(col.has("stage"), "Column has stage")
		assert_true(col.has("lai"), "Column has lai")
		assert_true(col.has("grain"), "Column has grain")
