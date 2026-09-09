extends GutTest

const Organs = preload("res://scripts/crop_organ_meshes.gd")


func _verts(mesh: ArrayMesh) -> PackedVector3Array:
	return mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]


func _extent(mesh: ArrayMesh) -> AABB:
	var verts := _verts(mesh)
	var box := AABB(verts[0], Vector3.ZERO)
	for v in verts:
		box = box.expand(v)
	return box


func test_spike_is_one_surface_reaching_its_length() -> void:
	var spike := Organs.build_spike(0.1, 0.02, 10, 0.06, 0.0, false, 3)
	assert_eq(spike.get_surface_count(), 1, "Whole spike is a single surface")
	var box := _extent(spike)
	assert_gt(box.end.y, 0.1, "Awns reach past the rachis tip")
	assert_lt(box.end.y, 0.1 + 0.06 + 0.02, "Awns stay within their length")
	assert_gt(box.size.x, 0.015, "Spikelets stand out on both sides")


func test_spike_bend_carries_tip_sideways() -> void:
	var straight := Organs.build_spike(0.2, 0.03, 12, 0.0, 0.0, true, 1)
	var bent := Organs.build_spike(0.2, 0.03, 12, 0.0, 2.0, true, 1)
	assert_lt(_extent(straight).end.z, 0.03, "Straight axis stays near the y axis")
	assert_gt(_extent(bent).end.z, 0.1, "Bent axis leans over towards +z")
	assert_lt(_extent(bent).end.y, _extent(straight).end.y, "Bent head is lower")


func test_spike_awnless_has_fewer_vertices() -> void:
	var awned := Organs.build_spike(0.1, 0.02, 10, 0.06, 0.0, false, 3)
	var awnless := Organs.build_spike(0.1, 0.02, 10, 0.0, 0.0, false, 3)
	assert_lt(_verts(awnless).size(), _verts(awned).size(), "No awn quads without awns")


func test_panicle_head_fills_its_envelope() -> void:
	var head := Organs.build_panicle_head(0.24, 0.05, 4)
	var box := _extent(head)
	assert_almost_eq(box.position.y, 0.0, 1e-4, "Head starts at the origin")
	assert_almost_eq(box.end.y, 0.24, 1e-4, "Head reaches its length")
	assert_gt(box.size.x, 0.08, "Head is about two radii wide")
	assert_lt(box.size.x, 0.13, "Lumps stay within +/-20% of the radius")


func test_bunch_hangs_down_and_colours_with_ripeness() -> void:
	var green := Organs.build_bunch(0.14, 0.045, 0.0, Color.GREEN, Color.PURPLE, 2)
	var ripe := Organs.build_bunch(0.14, 0.045, 1.0, Color.GREEN, Color.PURPLE, 2)
	var box := _extent(green)
	assert_lt(box.position.y, -0.12, "Bunch hangs down to about its length")
	assert_lte(box.end.y, 0.03, "Bunch starts near its peduncle")
	var green_cols: PackedColorArray = green.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
	var ripe_cols: PackedColorArray = ripe.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
	assert_eq(green_cols.size(), _verts(green).size(), "Every vertex carries a colour")
	var green_sum := 0.0
	var ripe_sum := 0.0
	for c in green_cols:
		green_sum += c.g - c.r
	for c in ripe_cols:
		ripe_sum += c.g - c.r
	assert_gt(green_sum, ripe_sum, "Ripe berries lose green for purple")


func test_bunch_turns_berry_by_berry() -> void:
	var turning := Organs.build_bunch(0.14, 0.045, 0.5, Color.GREEN, Color.PURPLE, 2)
	var cols: PackedColorArray = turning.surface_get_arrays(0)[Mesh.ARRAY_COLOR]
	var greens := 0
	var purples := 0
	for c in cols:
		if c.g > 0.6 and c.r < 0.3:
			greens += 1
		elif c.r > 0.3 and c.g < 0.3:
			purples += 1
	assert_gt(greens, 0, "Some berries still green at mid veraison")
	assert_gt(purples, 0, "Some berries already coloured at mid veraison")
