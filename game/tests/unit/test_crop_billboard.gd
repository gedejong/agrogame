extends GutTest

const CropBillboard = preload("res://scripts/crop_billboard.gd")


func test_plant_grid_constants() -> void:
	assert_eq(CropBillboard.PLANTS_H, 4, "4 horizontal plants")
	assert_eq(CropBillboard.PLANTS_V, 4, "4 vertical plants")


func test_stage_suffix_mapping() -> void:
	assert_eq(CropBillboard.STAGE_SUFFIX[0], "", "Stage 0 = no suffix")
	assert_eq(CropBillboard.STAGE_SUFFIX[1], "seedling")
	assert_eq(CropBillboard.STAGE_SUFFIX[2], "vegetative")
	assert_eq(CropBillboard.STAGE_SUFFIX[3], "flowering")
	assert_eq(CropBillboard.STAGE_SUFFIX[4], "mature")


func test_create_plants_count() -> void:
	var sprites := CropBillboard.create_plants(1.0, 0, 0)
	assert_eq(sprites.size(), 16, "16 sprites per tile (4x4)")
	for spr: Sprite3D in sprites:
		spr.queue_free()


func test_create_plants_billboard_mode() -> void:
	var sprites := CropBillboard.create_plants(1.0, 0, 0)
	var spr: Sprite3D = sprites[0]
	assert_eq(spr.billboard, BaseMaterial3D.BILLBOARD_ENABLED, "Billboard enabled")
	for s: Sprite3D in sprites:
		s.queue_free()
