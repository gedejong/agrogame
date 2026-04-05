extends GutTest

const Renderer = preload("res://scripts/maize_renderer_3d.gd")


func test_zero_growth_empty() -> void:
	var plant := Renderer.create_plant(0.0, 0.0, 0.0, 0.0, 0)
	assert_eq(plant.get_child_count(), 0, "No children at zero growth")
	plant.free()


func test_seedling_has_children() -> void:
	var plant := Renderer.create_plant(0.25, 0.0, 0.0, 0.0, 42)
	assert_gt(plant.get_child_count(), 0, "Seedling has geometry")
	plant.free()


func test_mature_has_more_children() -> void:
	var small := Renderer.create_plant(0.25, 0.0, 0.0, 0.0, 0)
	var large := Renderer.create_plant(1.0, 0.0, 0.0, 0.0, 0)
	assert_gt(large.get_child_count(), small.get_child_count(), "Mature > seedling")
	small.free()
	large.free()


func test_grain_adds_geometry() -> void:
	var no_grain := Renderer.create_plant(1.0, 0.0, 0.0, 0.0, 0)
	var with_grain := Renderer.create_plant(1.0, 0.0, 0.0, 0.5, 0)
	assert_gte(
		with_grain.get_child_count(), no_grain.get_child_count(), "Grain adds or keeps geometry"
	)
	no_grain.free()
	with_grain.free()
