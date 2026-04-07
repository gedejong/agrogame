extends GutTest
## Tests for CropVisuals static helper class.

const VisualsRef = preload("res://scripts/crop_visuals.gd")


func test_calc_growth_stage_0() -> void:
	assert_eq(VisualsRef._calc_growth(0, 0.5, 0.5), 0.0)


func test_calc_growth_stage_1() -> void:
	var g: float = VisualsRef._calc_growth(1, 0.5, 0.0)
	assert_gt(g, 0.04)
	assert_lt(g, 0.26)


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
	var plant: Node3D = VisualsRef.create_3d_plant("maize", 0.5, 0.0, 0.0, 0.0, 42)
	assert_not_null(plant)
	plant.queue_free()


func test_create_3d_plant_unknown_crop_returns_default() -> void:
	var plant: Node3D = VisualsRef.create_3d_plant("banana", 0.5, 0.0, 0.0, 0.0, 42)
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
