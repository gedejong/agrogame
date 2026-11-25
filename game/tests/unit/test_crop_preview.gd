extends GutTest

const CropPreviewRef = preload("res://scripts/crop_preview.gd")


func test_crops_list_defined() -> void:
	assert_eq(CropPreviewRef.CROPS.size(), 5, "5 crop types")
	assert_has(CropPreviewRef.CROPS, "maize")
	assert_has(CropPreviewRef.CROPS, "spring_wheat")


func test_slider_defs_defined() -> void:
	assert_eq(CropPreviewRef.SLIDER_DEFS.size(), 15, "15 slider parameters (#669 adds S, Mn)")
	var keys: Array[String] = []
	for def: Dictionary in CropPreviewRef.SLIDER_DEFS:
		keys.append(def["key"])
	assert_has(keys, "stage")
	assert_has(keys, "lai")
	assert_has(keys, "grain")
	assert_has(keys, "frost")
	assert_has(keys, "heat")
	assert_has(keys, "s")
	assert_has(keys, "mn")
	assert_has(keys, "sen_override")
	assert_has(keys, "wind")
	assert_has(keys, "wind_angle")


func test_lit_by_the_farm_environment() -> void:
	var preview: Node3D = CropPreviewRef.new()
	add_child_autofree(preview)
	var envs: Array[Node] = preview.find_children("*", "WorldEnvironment", false, false)
	assert_eq(envs.size(), 1, "One environment")
	assert_eq(
		(envs[0] as WorldEnvironment).environment,
		FarmViewDebug.FARM_ENVIRONMENT,
		"The preview shows the farm view's environment and tonemap"
	)
