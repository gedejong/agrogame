extends GutTest

const CropPreviewRef = preload("res://scripts/crop_preview.gd")


func test_crops_list_defined() -> void:
	assert_eq(CropPreviewRef.CROPS.size(), 5, "5 crop types")
	assert_has(CropPreviewRef.CROPS, "maize")
	assert_has(CropPreviewRef.CROPS, "spring_wheat")


func test_slider_defs_defined() -> void:
	assert_eq(CropPreviewRef.SLIDER_DEFS.size(), 8, "8 slider parameters")
	var keys: Array[String] = []
	for def: Dictionary in CropPreviewRef.SLIDER_DEFS:
		keys.append(def["key"])
	assert_has(keys, "growth")
	assert_has(keys, "senescence")
	assert_has(keys, "grain")
	assert_has(keys, "water")
