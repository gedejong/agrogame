extends RefCounted
## Procedural 3D wheat renderer.
## Single tiller with narrow blade leaves close to stem + seed head.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 1
const STEM_HEIGHT := 0.9
const LEAF_WIDTH := 0.02
const LEAF_LENGTH_FRAC := 0.4
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
		var stem_r: float = 0.003 * growth_progress + 0.001
		var stem := MeshInstance3D.new()
		stem.mesh = CR.create_stem_mesh(h, stem_r, stem_r * 0.6)
		stem.material_override = stem_mat
		stem.position = Vector3(offset_x, h * 0.5, offset_z)
		stem.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(stem)
		# Leaves: close to stem, ~40% of stem length.
		# During vegetative: extend all the way to the top.
		# During grain fill: leaves stay below the head.
		var leaf_top: float = 0.95 if not has_grain else 0.7
		var leaf_l: float = h * LEAF_LENGTH_FRAC * growth_progress
		var plant_rot: float = CR.hash_val(seed_val, 0) * TAU
		for li in range(NUM_LEAVES):
			var frac: float = float(li) / float(NUM_LEAVES)
			var y: float = h * (0.05 + frac * leaf_top)
			var azimuth: float = plant_rot + float(li) * PI
			azimuth += (CR.hash_val(seed_val, ti * 10 + 3 + li) - 0.5) * 0.6
			# Lower leaves droop more, upper leaves upright
			var droop: float = 0.1 + (1.0 - frac) * 0.3
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
		# Grain head at the top — only during flowering/maturity
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
