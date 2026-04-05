extends RefCounted
## Procedural 3D wheat renderer.
## The visible "stem" is leaf sheaths wrapped around each other (green).
## Free leaf blades emerge from the sheath at intervals.
## Bare peduncle + grain head only visible at flowering.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 1
const STEM_HEIGHT := 0.9
const LEAF_WIDTH := 0.03
const LEAF_LENGTH_FRAC := 0.25
const HEAD_RADIUS := 0.015
const HEAD_HEIGHT := 0.08
const NUM_LEAVES := 4


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
	var h: float = STEM_HEIGHT * pow(growth_progress, 2.0)
	var has_grain: bool = grain_frac > 0.01 and growth_progress > 0.6

	for ti in range(NUM_TILLERS):
		var offset_x: float = (CR.hash_val(seed_val, ti * 10) - 0.5) * 0.08
		var offset_z: float = (CR.hash_val(seed_val, ti * 10 + 1) - 0.5) * 0.08
		# Leaf sheath "stem": green cylinder formed by wrapped leaves.
		# Tapers from base to top. Always visible — this IS the plant body.
		var sheath_top: float = h * (0.8 if not has_grain else 0.7)
		var sheath_r_bot: float = 0.005 * growth_progress + 0.002
		var sheath_r_top: float = sheath_r_bot * 0.5
		var sheath_mat := CR.create_leaf_material("wheat", senescence, stress)
		var sheath := MeshInstance3D.new()
		sheath.mesh = CR.create_stem_mesh(sheath_top, sheath_r_bot, sheath_r_top)
		sheath.material_override = sheath_mat
		sheath.position = Vector3(offset_x, sheath_top * 0.5, offset_z)
		sheath.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(sheath)
		# Bare peduncle above sheaths — only at flowering
		if has_grain:
			var ped_h: float = h - sheath_top
			var stem_mat := CR.create_stem_material(senescence)
			var ped := MeshInstance3D.new()
			ped.mesh = CR.create_stem_mesh(ped_h, sheath_r_top * 0.6, sheath_r_top * 0.4)
			ped.material_override = stem_mat
			ped.position = Vector3(offset_x, sheath_top + ped_h * 0.5, offset_z)
			ped.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(ped)
		# Free leaf blades emerge from the sheath at intervals
		var leaf_l: float = h * LEAF_LENGTH_FRAC * growth_progress
		var plant_rot: float = CR.hash_val(seed_val, 0) * TAU
		for li in range(NUM_LEAVES):
			var frac: float = float(li) / float(NUM_LEAVES)
			# Leaves emerge from sheath at different heights
			var y: float = sheath_top * (0.3 + frac * 0.7)
			var azimuth: float = plant_rot + float(li) * PI
			azimuth += (CR.hash_val(seed_val, ti * 10 + 3 + li) - 0.5) * 0.4
			# Leaves are mostly upright near the sheath, tips curve out
			var droop: float = 0.08 + frac * 0.12
			var leaf_mesh := CR.build_curved_leaf(leaf_l, LEAF_WIDTH, droop, 3)
			var pivot := Node3D.new()
			pivot.position = Vector3(offset_x, y, offset_z)
			pivot.rotation.y = azimuth
			var leaf := MeshInstance3D.new()
			leaf.mesh = leaf_mesh
			leaf.material_override = leaf_mat
			leaf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			pivot.add_child(leaf)
			plant.add_child(pivot)
		# Grain head
		if has_grain:
			var head := MeshInstance3D.new()
			var head_mesh := CylinderMesh.new()
			head_mesh.height = HEAD_HEIGHT * grain_frac
			head_mesh.bottom_radius = HEAD_RADIUS
			head_mesh.top_radius = HEAD_RADIUS * 0.5
			head_mesh.radial_segments = 5
			head.mesh = head_mesh
			head.material_override = CR.create_grain_material(grain_frac)
			head.position = Vector3(offset_x, h + HEAD_HEIGHT * 0.3, offset_z)
			head.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(head)

	return plant
