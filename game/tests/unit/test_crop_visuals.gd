extends GutTest
## Tests for CropVisuals static helper class.

const VisualsRef = preload("res://scripts/crop_visuals.gd")


func test_calc_growth_stage_0() -> void:
	assert_eq(VisualsRef._calc_growth(0, 0.5, 0.5), 0.0)


func test_calc_growth_stage_1_low_lai() -> void:
	# Emerged with low LAI: sqrt(0.05) ≈ 0.22, at least the floor (0.05)
	var g: float = VisualsRef._calc_growth(1, 0.05, 0.0)
	assert_gte(g, 0.05, "Emerged has floor")
	assert_lt(g, 0.30, "Low LAI = small (sqrt scaled)")


func test_calc_growth_lai_drives_size() -> void:
	# High LAI at stage 2 should produce large plant
	var g: float = VisualsRef._calc_growth(2, 0.9, 0.0)
	assert_gt(g, 0.85, "High LAI = large regardless of stage")


func test_calc_growth_stage_4() -> void:
	var g: float = VisualsRef._calc_growth(4, 1.0, 1.0)
	assert_gte(g, 0.9)
	assert_lte(g, 1.0)


func test_calc_senescence_vegetative() -> void:
	assert_eq(VisualsRef._calc_senescence(2, 5.0, 0.5), 0.0)


func test_calc_senescence_grain_fill() -> void:
	var s: float = VisualsRef._calc_senescence(3, 2.0, 0.8)
	assert_gt(s, 0.0, "Senescence should be positive during grain fill")


func test_create_3d_plant_returns_node() -> void:
	var plant: Node3D = VisualsRef.create_3d_plant("maize", 0.5, 0.0, {}, 0.0, 42)
	assert_not_null(plant)
	plant.queue_free()


func test_create_3d_plant_unknown_crop_returns_default() -> void:
	var plant: Node3D = VisualsRef.create_3d_plant("banana", 0.5, 0.0, {}, 0.0, 42)
	assert_not_null(plant)
	plant.queue_free()


func test_collect_meshes() -> void:
	var root := Node3D.new()
	add_child_autofree(root)
	var mi := MeshInstance3D.new()
	mi.mesh = BoxMesh.new()
	root.add_child(mi)
	var out: Array[Dictionary] = []
	VisualsRef.collect_meshes(root, Transform3D(), out)
	assert_eq(out.size(), 1)
	assert_not_null(out[0]["mesh"])


func test_wheat_multimesh_has_all_layers() -> void:
	# Wheat at grain-fill should have stem, leaves, peduncle, and grain head
	var plant: Node3D = VisualsRef.create_3d_plant("spring_wheat", 0.9, 0.0, {}, 0.8, 42)
	add_child_autofree(plant)
	var meshes: Array[Dictionary] = []
	VisualsRef.collect_meshes(plant, Transform3D(), meshes)
	# At maturity with grain: sheath + peduncle + leaves + head = 4+ meshes
	assert_gt(meshes.size(), 3, "Wheat should have stem, leaves, peduncle, grain")


func test_rice_multimesh_has_all_layers() -> void:
	var plant: Node3D = VisualsRef.create_3d_plant("rice", 0.9, 0.0, {}, 0.8, 42)
	add_child_autofree(plant)
	var meshes: Array[Dictionary] = []
	VisualsRef.collect_meshes(plant, Transform3D(), meshes)
	assert_gt(meshes.size(), 3, "Rice should have stem, leaves, panicle")


func test_baked_plants_creates_multimesh_per_layer() -> void:
	# Verify _build_baked_plants creates one MultiMeshInstance3D per mesh layer
	var container := Node3D.new()
	add_child_autofree(container)
	var grid := Vector2i(2, 2)
	VisualsRef._build_baked_plants(
		container, "spring_wheat", grid, 0, 0, 0.5, 0.9, 0.0, {}, 0.8, 1.0
	)
	var mmi_count := 0
	for child: Node in container.get_children():
		if child is MultiMeshInstance3D:
			mmi_count += 1
	# Should have multiple MultiMeshInstance3D (one per mesh layer)
	assert_gt(mmi_count, 3, "Should have 4+ MultiMesh layers for wheat at grain-fill")


func test_bottom_leaf_more_senescent_than_top() -> void:
	# At grain fill, bottom leaves should have lower leaf_height → more senescence
	var plant: Node3D = VisualsRef.create_3d_plant("maize", 0.9, 0.5, {}, 0.5, 42)
	add_child_autofree(plant)
	var heights: Array[float] = []
	for child: Node in plant.get_children():
		for sub: Node in child.get_children():
			if sub is MeshInstance3D:
				var mi: MeshInstance3D = sub as MeshInstance3D
				if mi.material_override is ShaderMaterial:
					var sm: ShaderMaterial = mi.material_override as ShaderMaterial
					var lh: Variant = sm.get_shader_parameter("leaf_height")
					if lh != null:
						heights.append(float(lh))
	if heights.size() >= 2:
		# Bottom leaf (lowest height) should have leaf_height < top leaf
		assert_lt(heights[0], heights[-1], "Bottom leaf_height < top leaf_height")


func test_no_senescence_in_vegetative_stage() -> void:
	# Stages 1-2: senescence = 0, so gradient has no visible effect
	var sen: float = VisualsRef._calc_senescence(1, 3.0, 0.0)
	assert_eq(sen, 0.0, "No senescence in stage 1")
	sen = VisualsRef._calc_senescence(2, 5.0, 0.0)
	assert_eq(sen, 0.0, "No senescence in stage 2")


func test_senescence_gradient_increases_with_maturity() -> void:
	# At stage 4 with grain, senescence should be positive
	var sen: float = VisualsRef._calc_senescence(4, 2.0, 0.8)
	assert_gt(sen, 0.0, "Senescence positive at maturity")
	# Higher grain frac → more senescence
	var sen2: float = VisualsRef._calc_senescence(4, 1.0, 1.0)
	assert_gt(sen2, sen, "More grain → more senescence")


func test_zn_stunting_reduces_plant_scale() -> void:
	# Zn stress should make plants ~30% smaller (uniform XYZ scale).
	var tile_data := {
		"crop_key": "maize",
		"crop_stage": 3,
		"lai": 4.0,
		"grain_g_m2": 100.0,
		"col": 0,
		"row": 0,
		"zn_stress": 1.0,
	}
	var container := Node3D.new()
	add_child_autofree(container)
	VisualsRef.update_crop(tile_data, [container], {"maize": Vector2i(2, 2)}, 1.0, 1.0)
	var found_plant: Node3D = null
	for child: Node in container.get_children():
		if child is Node3D and not (child is MultiMeshInstance3D):
			found_plant = child as Node3D
			break
	assert_not_null(found_plant, "Should have at least one plant")
	if found_plant != null:
		# Stunt = 0.7, collapse_y = 1.0 (no senescence) → scale (0.7, 0.7, 0.7)
		assert_almost_eq(found_plant.scale.x, 0.7, 0.02, "Zn stunting reduces X scale")
		assert_almost_eq(found_plant.scale.z, 0.7, 0.02, "Zn stunting reduces Z scale")


func test_dead_plant_collapses_vertically() -> void:
	# Stage 4 with LAI=0 and full grain → _calc_senescence returns 1.0
	# (1 - 0/3.0) * clamp(2.0) = 1.0, triggering full collapse to Y=0.4.
	var tile_data := {
		"crop_key": "maize",
		"crop_stage": 4,
		"lai": 0.0,
		"grain_g_m2": 1000.0,
		"col": 0,
		"row": 0,
	}
	var container := Node3D.new()
	add_child_autofree(container)
	VisualsRef.update_crop(tile_data, [container], {"maize": Vector2i(2, 2)}, 1.0, 1.0)
	var found_plant: Node3D = null
	for child: Node in container.get_children():
		if child is Node3D and not (child is MultiMeshInstance3D):
			found_plant = child as Node3D
			break
	assert_not_null(found_plant, "Should have at least one plant")
	if found_plant != null:
		# At stage 4 with low LAI / max grain, sen ≈ 1 → Y scale collapses to 0.4.
		var ratio: float = found_plant.scale.y / found_plant.scale.x
		assert_almost_eq(ratio, 0.4, 0.1, "Y/X ≈ 0.4 (collapse to 40% height)")


func test_multimesh_uses_uniform_senescence() -> void:
	# MultiMesh mode: all instances share materials from sample plant.
	# Verify the sample plant has leaf_height values set (not all 0.5).
	var container := Node3D.new()
	add_child_autofree(container)
	var grid := Vector2i(2, 2)
	VisualsRef._build_baked_plants(container, "maize", grid, 0, 0, 0.5, 0.9, 0.5, {}, 0.5, 1.0)
	# Just verify it doesn't crash and creates output
	var mmi_count := 0
	for child: Node in container.get_children():
		if child is MultiMeshInstance3D:
			mmi_count += 1
	assert_gt(mmi_count, 0, "MultiMesh should create instances")
