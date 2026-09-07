extends GutTest

const CR = preload("res://scripts/crop_renderer_3d.gd")
const MaizeR = preload("res://scripts/maize_renderer_3d.gd")
const WheatR = preload("res://scripts/wheat_renderer_3d.gd")
const SorghumR = preload("res://scripts/sorghum_renderer_3d.gd")
const RiceR = preload("res://scripts/rice_renderer_3d.gd")
const GrapeR = preload("res://scripts/grape_renderer_3d.gd")


func test_hash_deterministic() -> void:
	var a: float = CR.hash_val(42, 7)
	var b: float = CR.hash_val(42, 7)
	assert_eq(a, b, "Same input = same output")


func test_hash_range() -> void:
	for s in range(10):
		for i in range(20):
			var v: float = CR.hash_val(s, i)
			assert_gte(v, 0.0)
			assert_lt(v, 1.0)


func test_leaf_masks_defined() -> void:
	for key: String in ["maize", "wheat", "sorghum", "rice", "grape"]:
		assert_true(CR.LEAF_MASKS.has(key), "Mask for %s" % key)


func test_maize_creates_children() -> void:
	var plant := MaizeR.create_plant(0.8, 0.0, {}, 0.0, 0)
	assert_gt(plant.get_child_count(), 0, "Maize has children at growth 0.8")
	plant.free()


func test_maize_empty_at_zero() -> void:
	var plant := MaizeR.create_plant(0.0, 0.0, {}, 0.0, 0)
	assert_eq(plant.get_child_count(), 0, "No children at zero growth")
	plant.free()


func test_wheat_creates_children() -> void:
	var plant := WheatR.create_plant(0.8, 0.0, {}, 0.0, 0)
	assert_gt(plant.get_child_count(), 0)
	plant.free()


func test_sorghum_creates_children() -> void:
	var plant := SorghumR.create_plant(0.8, 0.0, {}, 0.0, 0)
	assert_gt(plant.get_child_count(), 0)
	plant.free()


func test_rice_creates_children() -> void:
	var plant := RiceR.create_plant(0.8, 0.0, {}, 0.0, 0)
	assert_gt(plant.get_child_count(), 0)
	plant.free()


func test_grape_creates_children() -> void:
	var plant := GrapeR.create_plant(0.8, 0.0, {}, 0.0, 0)
	assert_gt(plant.get_child_count(), 0)
	plant.free()


func test_maize_grain_adds_ear() -> void:
	var no_grain := MaizeR.create_plant(1.0, 0.0, {}, 0.0, 0)
	var with_grain := MaizeR.create_plant(1.0, 0.0, {}, 0.5, 0)
	assert_gt(
		with_grain.get_child_count(),
		no_grain.get_child_count(),
		"Grain adds ear mesh",
	)
	no_grain.free()
	with_grain.free()


func test_organ_emergence_ramps_in_early_repro() -> void:
	assert_eq(CR.organ_emergence(0.0), 0.0)
	assert_between(CR.organ_emergence(0.05), 0.01, 0.99)
	assert_eq(CR.organ_emergence(0.5), 1.0)


func test_fill_scale_tracks_yield() -> void:
	assert_almost_eq(CR.fill_scale(0.0, 1.0), 0.6, 0.001, "Organs start at 60% size")
	assert_almost_eq(CR.fill_scale(1.0, 1.0), 1.0, 0.001, "Full yield fills to full size")
	assert_lt(CR.fill_scale(1.0, 0.3), CR.fill_scale(1.0, 1.0), "Poor grain set stays small")


func test_ripen_color_moves_green_to_ripe_to_dry() -> void:
	var green := Color(0.0, 1.0, 0.0)
	var ripe := Color(1.0, 1.0, 0.0)
	var dry := Color(0.5, 0.3, 0.1)
	assert_eq(CR.ripen_color(green, ripe, dry, 0.0, 0.0), green)
	assert_eq(CR.ripen_color(green, ripe, dry, 1.0, 0.0), ripe)
	var dried: Color = CR.ripen_color(green, ripe, dry, 1.0, 1.0)
	assert_lt(dried.g, ripe.g, "Senescence pulls the ripe colour towards dry")


func test_attach_mesh_adds_shadow_casting_child() -> void:
	var parent := Node3D.new()
	var inst := CR.attach_mesh(
		parent, BoxMesh.new(), CR.create_organ_material(Color.RED), Vector3.UP
	)
	assert_eq(inst.get_parent(), parent)
	assert_eq(inst.position, Vector3.UP)
	assert_eq(inst.cast_shadow, GeometryInstance3D.SHADOW_CASTING_SETTING_ON)
	assert_eq(inst.material_override.shader, CR.ORGAN_SHADER, "Organ material is wind-driven")
	parent.free()


func test_leaf_material_age_parameter() -> void:
	var young := CR.create_leaf_material("maize", 0.0, {}, 0.5, 0.2)
	var mature := CR.create_leaf_material("maize", 0.0, {}, 0.5)
	assert_almost_eq(young.get_shader_parameter("age"), 0.2, 0.001)
	assert_almost_eq(mature.get_shader_parameter("age"), 1.0, 0.001)


func test_curved_leaf_rise_override_flattens_arch() -> void:
	var arched: ArrayMesh = CR.build_curved_leaf(1.0, 0.1, 0.2, 6)
	var flat: ArrayMesh = CR.build_curved_leaf(1.0, 0.1, 0.2, 6, 0.0, 0.05)
	assert_lt(_max_y(flat), _max_y(arched), "Explicit small rise gives a lower arch")
	assert_gt(_max_y(flat), 0.0, "A small rise still lifts the blade")


func _max_y(mesh: ArrayMesh) -> float:
	var verts: PackedVector3Array = mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var top: float = -INF
	for v in verts:
		top = maxf(top, v.y)
	return top


func test_hash_neighbours_not_a_fixed_stride() -> void:
	# Adjacent plants (seed + 1) and successive leaves (idx + 1) must not
	# differ by a constant step: a fixed stride repeats as a visible pattern
	# across a whole stand.
	var seed_steps: Array[float] = []
	var idx_steps: Array[float] = []
	for k in range(24):
		seed_steps.append(fposmod(CR.hash_val(k + 1, 3) - CR.hash_val(k, 3), 1.0))
		idx_steps.append(fposmod(CR.hash_val(7, k + 1) - CR.hash_val(7, k), 1.0))
	assert_gt(_spread(seed_steps), 0.5, "Seed-to-seed step varies")
	assert_gt(_spread(idx_steps), 0.5, "Index-to-index step varies")
	# Roughly uniform: every decile of [0, 1) gets its share of 2000 draws.
	var buckets: Array[int] = []
	buckets.resize(10)
	buckets.fill(0)
	for sd in range(40):
		for i in range(50):
			buckets[int(CR.hash_val(sd, i) * 10.0)] += 1
	for b: int in buckets:
		assert_between(b, 130, 270, "Decile holds about a tenth of the draws (%d)" % b)


func _spread(values: Array[float]) -> float:
	var lo: float = values.min()
	var hi: float = values.max()
	return hi - lo
