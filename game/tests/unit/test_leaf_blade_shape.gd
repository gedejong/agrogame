extends GutTest
## Blade geometry built by crop_renderer_3d.gd: outline profile, keel,
## twist, sway and the per-crop material parameters that shade it.

const CR = preload("res://scripts/crop_renderer_3d.gd")


func test_leaf_material_sets_crop_colour_and_midrib() -> void:
	var maize := CR.create_leaf_material("maize", 0.0, {})
	var grape := CR.create_leaf_material("grape", 0.0, {})
	var maize_col: Vector3 = maize.get_shader_parameter("base_color")
	var grape_col: Vector3 = grape.get_shader_parameter("base_color")
	assert_ne(maize_col, grape_col, "Crops differ in blade colour")
	assert_gt(float(maize.get_shader_parameter("midrib")), 0.0, "Grass blades carry a midrib")
	assert_eq(float(grape.get_shader_parameter("midrib")), 0.0, "Palmate leaves have no midrib")


func test_leaf_shape_keel_lifts_edges_above_midrib() -> void:
	var flat := CR.build_curved_leaf(1.0, 0.2, 0.0, 6, 0.0, 0.0)
	var shape := CR.LeafShape.new()
	shape.keel = 0.5
	var keeled := CR.build_curved_leaf(1.0, 0.2, 0.0, 6, 0.0, 0.0, shape)
	assert_almost_eq(_max_y(flat), 0.0, 1e-5, "A flat blade with no rise lies in the plane")
	assert_gt(_max_y(keeled), 0.02, "Keel lifts the blade edges")


func test_leaf_shape_twist_and_sway_move_vertices_sideways() -> void:
	var shape := CR.LeafShape.new()
	shape.twist = 1.0
	var twisted := CR.build_curved_leaf(1.0, 0.2, 0.0, 6, 0.0, 0.0, shape)
	assert_gt(_max_y(twisted), 0.02, "Twist rotates the edges out of the plane")
	var sway := CR.LeafShape.new()
	sway.sway = 0.2
	var swayed := CR.build_curved_leaf(1.0, 0.2, 0.0, 6, 0.0, 0.0, sway)
	assert_gt(_max_x(swayed), 0.15, "Sway displaces the tip sideways")


func test_leaf_shape_peak_moves_widest_point() -> void:
	var shape := CR.LeafShape.new()
	shape.peak = 0.3
	var mesh := CR.build_curved_leaf(1.0, 0.2, 0.0, 10, 0.0, 0.0, shape)
	var verts: PackedVector3Array = mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var widest_z: float = 0.0
	var widest_x: float = 0.0
	for v in verts:
		if absf(v.x) > widest_x:
			widest_x = absf(v.x)
			widest_z = v.z
	assert_almost_eq(widest_z, 0.3, 0.11, "Widest ring sits at the peak position")
	assert_almost_eq(widest_x, 0.1, 0.01, "Peak width equals the given width")


func _max_x(mesh: ArrayMesh) -> float:
	var verts: PackedVector3Array = mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var best: float = -INF
	for v in verts:
		best = maxf(best, v.x)
	return best


func _max_y(mesh: ArrayMesh) -> float:
	var verts: PackedVector3Array = mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var top: float = -INF
	for v in verts:
		top = maxf(top, v.y)
	return top
