extends RefCounted
## Procedural 3D sorghum renderer.
## Thick stem, broad drooping leaves, dense spherical seed head.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const STEM_HEIGHT := 2.0
const LEAF_WIDTH := 0.07
const LEAF_LENGTH := 0.7
const MAX_LEAVES := 8
const HEAD_RADIUS := 0.06


static func create_plant(
	growth_progress: float,
	senescence: float,
	stresses: Dictionary,
	grain_frac: float,
	seed_val: int,
) -> Node3D:
	var plant := Node3D.new()
	if growth_progress < 0.05:
		return plant

	# Stem elongation: moderate curve, mostly grown by flowering.
	var h: float = STEM_HEIGHT * pow(growth_progress, 1.5)
	var sheath_mat := CR.create_leaf_material("sorghum", senescence, stresses, 0.3)
	# Leaf sheath: green cylinder (wrapped leaf bases = visible "stem")
	var has_grain: bool = grain_frac > 0.01 and growth_progress > 0.7
	var sheath_top: float = h * lerpf(0.9, 0.7, grain_frac)
	var sheath_r: float = 0.008 * growth_progress + 0.003
	var sheath := MeshInstance3D.new()
	sheath.mesh = CR.create_stem_mesh(sheath_top, sheath_r, sheath_r * 0.5)
	sheath.material_override = sheath_mat
	sheath.position = Vector3(0, sheath_top * 0.5, 0)
	sheath.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
	plant.add_child(sheath)
	# Bare peduncle at flowering
	if has_grain:
		var ped_h: float = h - sheath_top
		var ped := MeshInstance3D.new()
		ped.mesh = CR.create_stem_mesh(ped_h, sheath_r * 0.4, sheath_r * 0.3)
		ped.material_override = CR.create_stem_material(senescence)
		ped.position = Vector3(0, sheath_top + ped_h * 0.5, 0)
		ped.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(ped)
	# Broad drooping leaves with curve — ~120° phyllotaxis
	var leaf_top: float = lerpf(0.95, 0.75, grain_frac)
	var num_leaves: int = int(clampf(growth_progress, 0.0, 1.0) * MAX_LEAVES)
	var plant_rot: float = CR.hash_val(seed_val, 0) * TAU
	for li in range(num_leaves):
		var frac: float = float(li) / float(MAX_LEAVES)
		var y: float = (0.02 + frac * leaf_top) * h
		var azimuth: float = (
			plant_rot + float(li) * TAU / 3.0 + (CR.hash_val(seed_val, li * 3) - 0.5) * 0.7
		)
		var droop: float = 0.3 + (1.0 - frac) * 0.5 + CR.stress_droop_bonus(stresses)
		var leaf_l: float = LEAF_LENGTH * growth_progress
		var leaf_mesh := CR.build_curved_leaf(leaf_l, LEAF_WIDTH, droop, CR.leaf_segments)
		var pivot := Node3D.new()
		pivot.position = Vector3(0, y, 0)
		pivot.rotation.y = azimuth
		var leaf_h: float = clampf(y / maxf(h, 0.01), 0.0, 1.0)
		var leaf_mat := CR.create_leaf_material("sorghum", senescence, stresses, leaf_h)
		var leaf := MeshInstance3D.new()
		leaf.mesh = leaf_mesh
		leaf.material_override = leaf_mat
		leaf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		pivot.add_child(leaf)
		plant.add_child(pivot)
	# Dense spherical seed head
	if grain_frac > 0.01 and growth_progress > 0.7:
		var head := MeshInstance3D.new()
		var head_mesh := SphereMesh.new()
		head_mesh.radius = HEAD_RADIUS * grain_frac
		head_mesh.height = HEAD_RADIUS * 2.0 * grain_frac
		head_mesh.radial_segments = 8
		head_mesh.rings = 4
		head.mesh = head_mesh
		head.material_override = CR.create_grain_material(grain_frac)
		head.position = Vector3(0, h + HEAD_RADIUS, 0)
		head.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(head)

	return plant
