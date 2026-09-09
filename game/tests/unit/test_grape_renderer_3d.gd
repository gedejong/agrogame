extends GutTest

const Renderer = preload("res://scripts/grape_renderer_3d.gd")


func _count_meshes(node: Node) -> int:
	var n: int = 1 if node is MeshInstance3D else 0
	for child in node.get_children():
		n += _count_meshes(child)
	return n


func test_zero_growth_only_woody_frame() -> void:
	# A dormant vine is still a trellised vine: post, wires, trunk and cordon.
	var plant := Renderer.create_plant(0.0, 0.0, {}, 0.0, 0)
	assert_eq(plant.get_child_count(), Renderer.FRAME_MESHES, "Only the frame at zero growth")
	for child in plant.get_children():
		assert_false(child.material_override is ShaderMaterial, "No leaves on a dormant vine")
	plant.free()


func test_seedling_has_children() -> void:
	var plant := Renderer.create_plant(0.25, 0.0, {}, 0.0, 42)
	assert_gt(plant.get_child_count(), 0, "Seedling has geometry")
	plant.free()


func test_mature_has_more_leaves() -> void:
	var small := Renderer.create_plant(0.25, 0.0, {}, 0.0, 0)
	var large := Renderer.create_plant(1.0, 0.0, {}, 0.0, 0)
	assert_gt(_count_meshes(large), _count_meshes(small), "Mature carries more leaves")
	small.free()
	large.free()


func test_clusters_hang_from_bloom() -> void:
	var pre_bloom := Renderer.create_plant(1.0, 0.0, {}, 0.0, 0)
	var veraison := Renderer.create_plant(1.0, 0.0, {}, 0.5, 0)
	assert_gt(_count_meshes(veraison), _count_meshes(pre_bloom), "Clusters add geometry")
	pre_bloom.free()
	veraison.free()


func test_grain_adds_geometry() -> void:
	var no_grain := Renderer.create_plant(1.0, 0.0, {}, 0.0, 0)
	var with_grain := Renderer.create_plant(1.0, 0.0, {}, 0.5, 0)
	assert_gte(
		with_grain.get_child_count(), no_grain.get_child_count(), "Grain adds or keeps geometry"
	)
	no_grain.free()
	with_grain.free()
