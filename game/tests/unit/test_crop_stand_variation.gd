extends GutTest
## Plant-to-plant variation of a stand: unique seeds, placement scatter,
## natural lean, baked-instance size scatter and sample variants.

const VisualsRef = preload("res://scripts/crop_visuals.gd")


func test_plant_seeds_unique_within_field() -> void:
	# Every plant of a 4 x 4 tile field at the densest grid gets its own seed.
	var seen := {}
	for col in range(4):
		for row in range(4):
			for hi in range(10):
				for vi in range(40):
					seen[VisualsRef.plant_seed(col, row, hi, vi)] = true
	assert_eq(seen.size(), 4 * 4 * 10 * 40, "No two plants share a seed")


func test_plant_offset_bounded_and_varied() -> void:
	var grid := Vector2i(5, 8)
	var tile := 2.0
	var max_x: float = tile / 5.0 * VisualsRef.PLACEMENT_JITTER * 0.5
	var max_z: float = tile / 8.0 * VisualsRef.PLACEMENT_JITTER * 0.5
	var offsets: Array[Vector2] = []
	for sd in range(1, 21):
		var off: Vector2 = VisualsRef._plant_offset(sd, grid, tile)
		assert_lte(absf(off.x), max_x + 0.0001, "In-row scatter within bound")
		assert_lte(absf(off.y), max_z + 0.0001, "Between-row scatter within bound")
		offsets.append(off)
	var distinct := 0
	for k in range(1, offsets.size()):
		if offsets[0].distance_to(offsets[k]) > 0.005:
			distinct += 1
	assert_gt(distinct, 15, "Offsets differ from plant to plant")


func test_natural_lean_is_small_rotation_with_varied_azimuth() -> void:
	var dirs: Array[Vector2] = []
	for sd in range(1, 13):
		var b: Basis = VisualsRef.natural_lean_basis(sd)
		assert_almost_eq(b.determinant(), 1.0, 0.001, "Lean is a rotation")
		var up: Vector3 = b * Vector3.UP
		assert_gte(up.y, cos(VisualsRef.NATURAL_LEAN_RAD) - 0.0001, "Lean stays slight")
		dirs.append(Vector2(up.x, up.z).normalized())
	var varied := 0
	for k in range(1, dirs.size()):
		if dirs[0].distance_to(dirs[k]) > 0.1:
			varied += 1
	assert_gt(varied, 8, "Lean azimuth differs between plants")


func test_baked_instance_size_scatter() -> void:
	var lo: float = pow(1.0 - VisualsRef.VIGOUR_SCATTER, 3.0)
	var hi: float = pow(1.0 + VisualsRef.VIGOUR_SCATTER, 3.0)
	var dets: Array[float] = []
	for sd in range(1, 21):
		var d: float = VisualsRef._baked_instance_basis(sd, 1.0, 1.0, 0.0).determinant()
		assert_between(d, lo - 0.0001, hi + 0.0001, "Instance volume within vigour scatter")
		dets.append(d)
	assert_gt(dets.max() / dets.min(), 1.05, "Instances differ in size")


func test_baked_tile_mixes_sample_variants() -> void:
	var container := Node3D.new()
	add_child_autofree(container)
	var grid := Vector2i(5, 8)
	var stresses := {}
	VisualsRef._build_baked_plants(
		container, "maize", grid, 0, 0, 0.5, 0.9, 0.1, stresses, 0.5, 1.0
	)
	# Layers of one sample plant, for comparison.
	var sample: Node3D = VisualsRef.create_3d_plant("maize", 0.9, 0.1, stresses, 0.5, 12345, 1.0)
	var layers: Array[Dictionary] = []
	VisualsRef.collect_meshes(sample, Transform3D(), layers)
	sample.free()
	var total: int = grid.x * grid.y
	var mmi_count := 0
	var instances := 0
	for child: Node in container.get_children():
		if child is MultiMeshInstance3D:
			mmi_count += 1
			var n: int = (child as MultiMeshInstance3D).multimesh.instance_count
			assert_between(n, 1, total - 1, "Each variant draws a proper subset of the tile")
			instances += n
	assert_gt(mmi_count, layers.size(), "More layers than one sample plant: several variants")
	assert_eq(instances, total * layers.size(), "Every plant drawn once per layer")
