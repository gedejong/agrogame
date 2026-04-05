extends RefCounted
## Procedural 3D wheat renderer.
## Cluster of thin stems with narrow blade leaves + seed head.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 4
const STEM_HEIGHT := 0.18
const LEAF_WIDTH := 0.008
const LEAF_LENGTH := 0.06
const HEAD_RADIUS := 0.005
const HEAD_HEIGHT := 0.02


static func create_plant(
	growth_progress: float,
	senescence: float,
	stress: float,
	grain_frac: float,
	seed_val: int,
) -> Node3D:
	var plant := Node3D.new()
	if growth_progress < 0.05:
		return plant

	var leaf_mat := CR.create_leaf_material("wheat", senescence, stress)
	var stem_mat := CR.create_stem_material(senescence)
	var h: float = STEM_HEIGHT * growth_progress

	for ti in range(NUM_TILLERS):
		var offset_x: float = (CR.hash_val(seed_val, ti * 10) - 0.5) * 0.015
		var offset_z: float = (CR.hash_val(seed_val, ti * 10 + 1) - 0.5) * 0.015
		# Stem
		var stem := MeshInstance3D.new()
		stem.mesh = CR.create_stem_mesh(h, 0.002, 0.001)
		stem.material_override = stem_mat
		stem.position = Vector3(offset_x, h * 0.5, offset_z)
		stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(stem)
		# 2-3 leaves per tiller
		var num_leaves: int = 2 + int(CR.hash_val(seed_val, ti * 10 + 2))
		for li in range(num_leaves):
			var y: float = h * (0.2 + float(li) * 0.3)
			var angle: float = CR.hash_val(seed_val, ti * 10 + 3 + li) * TAU
			var droop: float = 0.3 + CR.hash_val(seed_val, ti * 10 + 6 + li) * 0.5
			var leaf := CR.create_leaf_quad(
				LEAF_WIDTH, LEAF_LENGTH * growth_progress, Vector3.ZERO, Vector3.ZERO
			)
			leaf.material_override = leaf_mat
			leaf.position = Vector3(offset_x, y, offset_z)
			leaf.rotation = Vector3(-droop, angle, 0)
			plant.add_child(leaf)
		# Seed head at top
		if grain_frac > 0.01 and growth_progress > 0.6:
			var head := MeshInstance3D.new()
			var head_mesh := CylinderMesh.new()
			head_mesh.height = HEAD_HEIGHT * grain_frac
			head_mesh.bottom_radius = HEAD_RADIUS
			head_mesh.top_radius = HEAD_RADIUS * 0.5
			head_mesh.radial_segments = 5
			head.mesh = head_mesh
			head.material_override = CR.create_grain_material(grain_frac)
			head.position = Vector3(offset_x, h + HEAD_HEIGHT * 0.5, offset_z)
			head.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(head)

	return plant
