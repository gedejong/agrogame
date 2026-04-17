extends RefCounted
## Procedural 3D rice renderer.
## Thin stems with narrow blades, drooping panicle at maturity.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const NUM_TILLERS := 4
const STEM_HEIGHT := 1.0
const LEAF_WIDTH := 0.035
const LEAF_LENGTH := 0.45
const PANICLE_HEIGHT := 0.06


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

	# Per-leaf materials created in loop for bottom-up senescence
	var stem_mat := CR.create_stem_material(senescence, 0.9)
	# Stem elongation: moderate curve, mostly grown by flowering.
	var h: float = STEM_HEIGHT * pow(growth_progress, 1.3)

	for ti in range(NUM_TILLERS):
		# Tillers splay outward from shared base
		var tiller_angle: float = float(ti) * TAU / float(NUM_TILLERS)
		tiller_angle += CR.hash_val(seed_val, ti * 8) * 0.5
		var splay: float = 0.03 + CR.hash_val(seed_val, ti * 8 + 1) * 0.03
		var ox: float = cos(tiller_angle) * splay
		var oz: float = sin(tiller_angle) * splay
		var has_grain: bool = grain_frac > 0.01 and growth_progress > 0.6
		# Each tiller slightly different height (±10%)
		var th: float = h * (0.9 + CR.hash_val(seed_val, ti * 8 + 2) * 0.2)
		# Leaf sheath: full height when no grain, recedes when peduncle appears
		var sheath_top: float = th if not has_grain else th * lerpf(0.85, 0.7, grain_frac)
		var sheath_r: float = 0.004 * growth_progress + 0.002
		var sheath := MeshInstance3D.new()
		sheath.mesh = CR.create_stem_mesh(sheath_top, sheath_r, sheath_r * 0.5)
		sheath.material_override = CR.create_leaf_material("rice", senescence, stresses, 0.3)
		sheath.position = Vector3(ox, sheath_top * 0.5, oz)
		sheath.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
		plant.add_child(sheath)
		# Bare peduncle above sheath at grain fill
		if has_grain and sheath_top < th:
			var ped_h: float = th - sheath_top
			var ped := MeshInstance3D.new()
			ped.mesh = CR.create_stem_mesh(ped_h, sheath_r * 0.4, sheath_r * 0.3)
			ped.material_override = stem_mat
			ped.position = Vector3(ox, sheath_top + ped_h * 0.5, oz)
			ped.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(ped)
		# Free leaf blades emerging along full tiller height
		var plant_rot: float = CR.hash_val(seed_val, ti * 7) * TAU
		for li in range(3):
			var y: float = th * (0.2 + float(li) / 3.0 * 0.7)
			var azimuth: float = (
				plant_rot
				+ float(li) * TAU / 3.0
				+ (CR.hash_val(seed_val, ti * 8 + 3 + li) - 0.5) * 0.8
			)
			var droop: float = 0.05 + CR.hash_val(seed_val, ti * 8 + 5 + li) * 0.12
			var leaf_l: float = LEAF_LENGTH * growth_progress
			var leaf_mesh := CR.build_curved_leaf(leaf_l, LEAF_WIDTH, droop, CR.leaf_segments)
			var pivot := Node3D.new()
			pivot.position = Vector3(ox, y, oz)
			pivot.rotation.y = azimuth
			var leaf_h: float = clampf(y / maxf(th, 0.01), 0.0, 1.0)
			var leaf_mat := CR.create_leaf_material("rice", senescence, stresses, leaf_h)
			var leaf := MeshInstance3D.new()
			leaf.mesh = leaf_mesh
			leaf.material_override = leaf_mat
			leaf.rotation.x = CR.stress_droop_bonus(stresses) * 1.2
			leaf.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			pivot.add_child(leaf)
			plant.add_child(pivot)
		# Drooping panicle
		if grain_frac > 0.01 and growth_progress > 0.6:
			var pan := MeshInstance3D.new()
			var pan_mesh := CylinderMesh.new()
			pan_mesh.height = PANICLE_HEIGHT * grain_frac
			pan_mesh.bottom_radius = 0.003 * grain_frac
			pan_mesh.top_radius = 0.001 * grain_frac
			pan_mesh.radial_segments = 5
			pan.mesh = pan_mesh
			pan.material_override = CR.create_grain_material(grain_frac)
			pan.position = Vector3(ox, th + 0.005, oz)
			pan.rotation.x = 0.5 + grain_frac * 0.5
			pan.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON
			plant.add_child(pan)

	return plant
