extends RefCounted
## Procedural 3D rice renderer.
## Thin stems with narrow blades, drooping panicle at maturity.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 1
const STEM_HEIGHT := 1.0
const LEAF_WIDTH := 0.015
const LEAF_LENGTH := 0.4
const PANICLE_HEIGHT := 0.06


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
	var h: float = STEM_HEIGHT * pow(growth_progress, 2.0)

	for ti in range(NUM_TILLERS):
		var ox: float = (CR.hash_val(seed_val, ti * 8) - 0.5) * 0.06
		var oz: float = (CR.hash_val(seed_val, ti * 8 + 1) - 0.5) * 0.06
		var has_grain: bool = grain_frac > 0.01 and growth_progress > 0.6
		# Leaf sheath: green cylinder (wrapped leaves form the visible "stem")
		var sheath_top: float = h * (0.85 if not has_grain else 0.7)
		var sheath_r: float = 0.003 * growth_progress + 0.001
		var sheath := MeshInstance3D.new()
		sheath.mesh = CR.create_stem_mesh(sheath_top, sheath_r, sheath_r * 0.5)
		sheath.material_override = leaf_mat
		sheath.position = Vector3(ox, sheath_top * 0.5, oz)
		sheath.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(sheath)
		# Bare peduncle above sheath at grain fill
		if has_grain:
			var ped_h: float = h - sheath_top
			var ped := MeshInstance3D.new()
			ped.mesh = CR.create_stem_mesh(ped_h, sheath_r * 0.4, sheath_r * 0.3)
			ped.material_override = stem_mat
			ped.position = Vector3(ox, sheath_top + ped_h * 0.5, oz)
			ped.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(ped)
		# Free leaf blades emerging from the sheath
		var plant_rot: float = CR.hash_val(seed_val, 0) * TAU
		for li in range(3):
			var y: float = sheath_top * (0.3 + float(li) / 3.0 * 0.7)
			var azimuth: float = (
				plant_rot + float(li) * PI + (CR.hash_val(seed_val, ti * 8 + 2 + li) - 0.5) * 0.6
			)
			var droop: float = 0.05 + CR.hash_val(seed_val, ti * 8 + 5 + li) * 0.12
			var leaf_l: float = LEAF_LENGTH * growth_progress
			var leaf_mesh := CR.build_curved_leaf(leaf_l, LEAF_WIDTH, droop, 4)
			var pivot := Node3D.new()
			pivot.position = Vector3(ox, y, oz)
			pivot.rotation.y = azimuth
			var leaf := MeshInstance3D.new()
			leaf.mesh = leaf_mesh
			leaf.material_override = leaf_mat
			leaf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			pivot.add_child(leaf)
			plant.add_child(pivot)
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
