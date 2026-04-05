extends RefCounted
## Procedural 3D wheat renderer.
## Grass-like: leaves sheath the stem, hiding it. Only the peduncle
## (top of stem above flag leaf) is visible during flowering/grain fill.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 1
const STEM_HEIGHT := 0.9
const LEAF_WIDTH := 0.012
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
	var stem_mat := CR.create_stem_material(senescence)
	var h: float = STEM_HEIGHT * pow(growth_progress, 2.0)
	var has_grain: bool = grain_frac > 0.01 and growth_progress > 0.6

	for ti in range(NUM_TILLERS):
		var offset_x: float = (CR.hash_val(seed_val, ti * 10) - 0.5) * 0.08
		var offset_z: float = (CR.hash_val(seed_val, ti * 10 + 1) - 0.5) * 0.08
		# Stem: only the exposed peduncle above the flag leaf is visible.
		# During vegetative: no visible stem (hidden by leaf sheaths).
		# During flowering: short bare section at top.
		if has_grain:
			var peduncle_h: float = h * 0.2
			var peduncle_y: float = h - peduncle_h * 0.5
			var stem_r: float = 0.002 * growth_progress + 0.001
			var stem := MeshInstance3D.new()
			stem.mesh = CR.create_stem_mesh(peduncle_h, stem_r, stem_r * 0.7)
			stem.material_override = stem_mat
			stem.position = Vector3(offset_x, peduncle_y, offset_z)
			stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(stem)
		# Leaves: tightly upright, hugging the stem axis.
		# They form the visible "body" of the plant.
		var leaf_top: float = 0.95 if not has_grain else 0.75
		var leaf_l: float = h * LEAF_LENGTH_FRAC * growth_progress
		var plant_rot: float = CR.hash_val(seed_val, 0) * TAU
		for li in range(NUM_LEAVES):
			var frac: float = float(li) / float(NUM_LEAVES)
			var y: float = h * (0.02 + frac * leaf_top)
			var azimuth: float = plant_rot + float(li) * PI
			azimuth += (CR.hash_val(seed_val, ti * 10 + 3 + li) - 0.5) * 0.4
			# Very low droop — leaves hug the stem, mostly upright
			var droop: float = 0.05 + (1.0 - frac) * 0.1
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
		# Grain head at the top
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
