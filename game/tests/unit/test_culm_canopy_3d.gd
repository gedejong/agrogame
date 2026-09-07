extends GutTest

const Canopy = preload("res://scripts/culm_canopy_3d.gd")
const MaizeR = preload("res://scripts/maize_renderer_3d.gd")


func _params() -> Canopy.Params:
	return MaizeR.canopy_params()


func test_nodes_climb_and_crowd_near_the_base() -> void:
	var p := _params()
	var lo: float = Canopy.node_frac(p, 0.0)
	var mid: float = Canopy.node_frac(p, 0.5)
	var top: float = Canopy.node_frac(p, 1.0)
	assert_lt(lo, mid, "Nodes climb with leaf index")
	assert_lt(mid, top, "Nodes climb with leaf index")
	assert_lt(mid - lo, top - mid, "Internodes lengthen up the culm")
	assert_almost_eq(top, 0.03 + p.top_node_frac, 1e-6, "Top node sits at top_node_frac")


func test_leaves_expand_in_sequence() -> void:
	var p := _params()
	assert_eq(Canopy.leaf_expansion(p, 0.5, 0.0), 1.0, "Lowest leaf long expanded at mid growth")
	assert_eq(Canopy.leaf_expansion(p, 0.5, 1.0), 0.0, "Top leaf not yet appeared at mid growth")
	var partial: float = Canopy.leaf_expansion(p, 0.5, 0.55)
	assert_gt(partial, 0.0, "Whorl leaf is unfolding")
	assert_lt(partial, 1.0, "Whorl leaf is unfolding")


func test_stalk_ends_inside_whorl_before_heading() -> void:
	var p := _params()
	assert_lt(Canopy.stalk_frac(p, 0.5), 0.6, "Mid-growth culm stays well below final height")
	assert_lt(Canopy.stalk_frac(p, 1.0), 1.0, "Even a full canopy leaves the peduncle unstretched")
	assert_gt(Canopy.stalk_frac(p, 1.0), Canopy.stalk_frac(p, 0.5), "Culm grows with the canopy")


func test_add_leaves_count_follows_growth_not_seed() -> void:
	var p := _params()
	var counts: Array[int] = []
	for seed_val in [1, 2, 3]:
		var plant := Node3D.new()
		Canopy.add_leaves(plant, p, 2.0, 1.5, 0.5, 0.0, 0.0, {}, seed_val, 0.03)
		counts.append(plant.get_child_count())
		plant.free()
	assert_eq(counts[0], counts[1], "Leaf count is independent of the seed")
	assert_eq(counts[1], counts[2], "Leaf count is independent of the seed")
	var full := Node3D.new()
	Canopy.add_leaves(full, p, 2.0, 2.0, 1.0, 0.0, 0.0, {}, 1, 0.03)
	assert_eq(full.get_child_count(), p.max_leaves, "Full growth carries every leaf")
	assert_gt(full.get_child_count(), counts[0], "More leaves at full growth than at half")
	full.free()


func test_heading_unfolds_whole_canopy() -> void:
	var p := _params()
	var headed := Node3D.new()
	Canopy.add_leaves(headed, p, 2.0, 2.0, 0.6, 1.0, 0.0, {}, 5, 0.03)
	assert_eq(headed.get_child_count(), p.max_leaves, "Emergence brings out every leaf")
	headed.free()


func test_leaves_never_attach_above_stalk_top() -> void:
	var p := _params()
	var plant := Node3D.new()
	Canopy.add_leaves(plant, p, 2.0, 1.2, 0.9, 0.0, 0.0, {}, 9, 0.03)
	for pivot in plant.get_children():
		assert_lte((pivot as Node3D).position.y, 1.2 + 1e-6, "Node clamped to the drawn culm")
	plant.free()


func test_blade_size_ladder() -> void:
	var p := _params()
	p.size_centre = 0.6
	p.size_falloff = 2.8
	p.size_min = 0.2
	assert_almost_eq(Canopy.blade_size(p, 0.0), 0.2, 1e-6, "Lowest leaf at size_min")
	assert_almost_eq(Canopy.blade_size(p, 0.6), 1.0, 1e-6, "Largest leaf at size_centre")
	var prev: float = 0.0
	for i in range(7):
		var size: float = Canopy.blade_size(p, float(i) / 10.0)
		assert_gt(size, prev - 1e-6, "Blade size rises to the centre")
		prev = size
	assert_almost_eq(Canopy.blade_size(p, 1.0), 1.0 - 2.8 * 0.16, 1e-6, "Top leaf on the parabola")
	p.size_falloff = 20.0
	assert_almost_eq(Canopy.blade_size(p, 1.0), 0.2, 1e-6, "Never below size_min past the centre")


func test_small_blades_stand_erect_large_ones_sag() -> void:
	assert_almost_eq(
		Canopy.sag_weight(Canopy.SAG_SIZE_MIN), 0.0, 1e-6, "No sag below the size floor"
	)
	assert_almost_eq(Canopy.sag_weight(Canopy.SAG_SIZE_FULL), 1.0, 1e-6, "Full sag at full size")
	assert_gt(Canopy.sag_weight(0.6), Canopy.sag_weight(0.4), "Sag grows with size")
	# The same species angles for every leaf: only size separates the postures.
	var p := _params()
	p.tilt_low = 0.6
	p.tilt_high = 0.6
	p.droop_low = 0.7
	p.droop_high = 0.7
	p.size_centre = 0.6
	p.size_min = 0.2
	var plant := Node3D.new()
	add_child_autofree(plant)
	Canopy.add_leaves(plant, p, 2.0, 2.0, 1.0, 1.0, 0.0, {}, 11, 0.01)
	var lowest: MeshInstance3D = _leaf_mesh(plant, 0)
	var largest: MeshInstance3D = _leaf_mesh(plant, int(round(0.6 * float(p.max_leaves - 1))))
	# rotation.x = -tilt: the short lowest blade points up more steeply than
	# the full-sized blade, by more than the tilt jitter can close.
	assert_lt(lowest.rotation.x, largest.rotation.x - 0.25, "Short lowest blade stands erect")


func _leaf_mesh(plant: Node3D, index: int) -> MeshInstance3D:
	var pivot: Node3D = plant.get_child(index) as Node3D
	return pivot.get_child(0) as MeshInstance3D
