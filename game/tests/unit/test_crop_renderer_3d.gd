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
