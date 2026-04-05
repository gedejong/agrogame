extends RefCounted
## Procedural 3D wheat renderer.
## Cluster of thin stems with narrow blade leaves + seed head.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 4
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
	var h: float = STEM_HEIGHT * growth_progress

	for ti in range(NUM_TILLERS):
		var offset_x: float = (CR.hash_val(seed_val, ti * 10) - 0.5) * 0.08
		var offset_z: float = (CR.hash_val(seed_val, ti * 10 + 1) - 0.5) * 0.08
		# Stem
		var stem := MeshInstance3D.new()
		stem.mesh = CR.create_stem_mesh(h, 0.008, 0.004)
		stem.material_override = stem_mat
		stem.position = Vector3(offset_x, h * 0.5, offset_z)
		stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(stem)
		# 3-4 leaves per tiller, alternating ~180° with variation
		var num_leaves: int = 3 + int(CR.hash_val(seed_val, ti * 10 + 2))
		for li in range(num_leaves):
			var y: float = h * (0.15 + float(li) * 0.2)
			var azimuth: float = (
				float(li) * PI + (CR.hash_val(seed_val, ti * 10 + 3 + li) - 0.5) * 0.8
			)
			var droop: float = 0.3 + (1.0 - float(li) / float(num_leaves)) * 0.5
			var pivot := Node3D.new()
			pivot.position = Vector3(offset_x, y, offset_z)
			pivot.rotation.y = azimuth
			var leaf := CR.create_leaf_quad(
				LEAF_WIDTH, LEAF_LENGTH * growth_progress, Vector3.ZERO, Vector3.ZERO
			)
			leaf.material_override = leaf_mat
			leaf.position = Vector3(0, 0, LEAF_LENGTH * growth_progress * 0.4)
			leaf.rotation.x = -droop
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
