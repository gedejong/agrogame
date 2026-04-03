extends GutTest

const CropRenderer = preload("res://scripts/crop_renderer.gd")


func test_crop_sprite_path_maize() -> void:
	var path: String = CropRenderer.crop_sprite_path("maize", "seedling")
	assert_eq(path, "res://assets/crops/maize_seedling.svg")


func test_crop_sprite_path_wheat_alias() -> void:
	var path: String = CropRenderer.crop_sprite_path("spring_wheat", "flowering")
	assert_eq(path, "res://assets/crops/wheat_flowering.svg")


func test_fallback_crop() -> void:
	assert_eq(CropRenderer._FALLBACK_CROP, "maize")
