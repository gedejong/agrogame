extends RefCounted
## Procedural 3D rice renderer.
## Thin stems with narrow blades, drooping panicle at maturity.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 5
const STEM_HEIGHT := 0.15
const LEAF_WIDTH := 0.005
const LEAF_LENGTH := 0.05
const PANICLE_HEIGHT := 0.015


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

	var leaf_mat := CR.create_leaf_material("rice", senescence, stress)
	var stem_mat := CR.create_stem_material(senescence)
	var h: float = STEM_HEIGHT * growth_progress

	for ti in range(NUM_TILLERS):
		var ox: float = (CR.hash_val(seed_val, ti * 8) - 0.5) * 0.012
		var oz: float = (CR.hash_val(seed_val, ti * 8 + 1) - 0.5) * 0.012
		var stem := MeshInstance3D.new()
		stem.mesh = CR.create_stem_mesh(h, 0.0015, 0.001)
		stem.material_override = stem_mat
		stem.position = Vector3(ox, h * 0.5, oz)
		stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(stem)
		# Narrow leaves
		for li in range(3):
			var y: float = h * (0.15 + float(li) * 0.25)
			var angle: float = CR.hash_val(seed_val, ti * 8 + 2 + li) * TAU
			var droop: float = 0.2 + CR.hash_val(seed_val, ti * 8 + 5 + li) * 0.4
			var leaf := CR.create_leaf_quad(
				LEAF_WIDTH, LEAF_LENGTH * growth_progress, Vector3.ZERO, Vector3.ZERO
			)
			leaf.material_override = leaf_mat
			leaf.position = Vector3(ox, y, oz)
			leaf.rotation = Vector3(-droop, angle, 0)
			plant.add_child(leaf)
		# Drooping panicle
		if grain_frac > 0.01 and growth_progress > 0.6:
			var pan := MeshInstance3D.new()
			var pan_mesh := CylinderMesh.new()
			pan_mesh.height = PANICLE_HEIGHT * grain_frac
			pan_mesh.bottom_radius = 0.003
			pan_mesh.top_radius = 0.001
			pan_mesh.radial_segments = 5
			pan.mesh = pan_mesh
			pan.material_override = CR.create_grain_material(grain_frac)
			pan.position = Vector3(ox, h + 0.005, oz)
			pan.rotation.x = 0.5 + grain_frac * 0.5
			pan.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(pan)

	return plant
