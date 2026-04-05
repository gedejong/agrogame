extends RefCounted
## Procedural 3D wheat renderer.
## Cluster of thin stems with narrow blade leaves + seed head.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 1
const STEM_HEIGHT := 0.9
const LEAF_WIDTH := 0.02
const LEAF_LENGTH := 0.3
const HEAD_RADIUS := 0.015
const HEAD_HEIGHT := 0.08


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
	var h: float = STEM_HEIGHT * pow(growth_progress, 2.0)

	for ti in range(NUM_TILLERS):
		var offset_x: float = (CR.hash_val(seed_val, ti * 10) - 0.5) * 0.08
		var offset_z: float = (CR.hash_val(seed_val, ti * 10 + 1) - 0.5) * 0.08
		# Stem — thin, scales with growth
		var stem_r: float = 0.003 * growth_progress + 0.001
		var stem := MeshInstance3D.new()
		stem.mesh = CR.create_stem_mesh(h, stem_r, stem_r * 0.6)
		stem.material_override = stem_mat
		stem.position = Vector3(offset_x, h * 0.5, offset_z)
		stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(stem)
		# 3-4 leaves distributed along stem with curved droop
		var num_leaves: int = 3 + int(CR.hash_val(seed_val, ti * 10 + 2))
		for li in range(num_leaves):
			var y: float = h * (0.1 + float(li) / float(num_leaves) * 0.75)
			var azimuth: float = (
				float(li) * PI + (CR.hash_val(seed_val, ti * 10 + 3 + li) - 0.5) * 0.8
			)
			var droop: float = 0.2 + (1.0 - float(li) / float(num_leaves)) * 0.4
			var leaf_l: float = LEAF_LENGTH * growth_progress
			var leaf_mesh := CR.build_curved_leaf(leaf_l, LEAF_WIDTH, droop, 4)
			var pivot := Node3D.new()
			pivot.position = Vector3(offset_x, y, offset_z)
			pivot.rotation.y = azimuth
			var leaf := MeshInstance3D.new()
			leaf.mesh = leaf_mesh
			leaf.material_override = leaf_mat
			leaf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			pivot.add_child(leaf)
			plant.add_child(pivot)
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
