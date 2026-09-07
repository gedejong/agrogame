extends RefCounted
## Procedural 3D rice renderer.
## A hill of tillers from one crown. Each tiller is a sheath column with
## erect, narrow, keeled blades and, once headed (repro > 0), an exserted
## peduncle carrying a spiral panicle: upright and green at heading, then
## bending over and turning golden as the grains fill and ripen.

const CR = preload("res://scripts/crop_renderer_3d.gd")
const Organs = preload("res://scripts/crop_organ_meshes.gd")

const NUM_TILLERS := 7
const STEM_HEIGHT := 0.9
const NUM_LEAVES := 3
const LEAF_WIDTH := 0.018
const LEAF_LENGTH := 0.45
## Arch height of a blade relative to its length: rice blades stand nearly
## straight and bend outward only towards the tip.
const BLADE_RISE := 0.08
## Blade outline: widest well out along the blade and broad at the collar,
## with a keel that flattens towards the tip.
const BLADE_PEAK := 0.4
const BLADE_BASE_FRAC := 0.8
const BLADE_KEEL := 0.35
const PANICLE_LENGTH := 0.22
const PANICLE_WIDTH := 0.028
const SPIKELETS := 12
## Fraction of tiller height exposed as bare peduncle after heading.
const PEDUNCLE_FRAC := 0.2
## Bend of the panicle axis (rad) at heading and when ripe: filled grains
## weigh the panicle over until it hangs.
const PANICLE_BEND_GREEN := 0.5
const PANICLE_BEND_RIPE := 2.0

const PANICLE_GREEN := Color(0.50, 0.63, 0.30)
const PANICLE_RIPE := Color(0.85, 0.70, 0.32)
const PANICLE_DRY := Color(0.72, 0.58, 0.30)
## The sheath column is leaf tissue: leaf green, drying to straw.
const SHEATH_GREEN := Color(0.27, 0.56, 0.18)


static func create_plant(
	growth_progress: float,
	senescence: float,
	stresses: Dictionary,
	repro: float,
	seed_val: int,
	yield_frac: float = 1.0
) -> Node3D:
	var plant := Node3D.new()
	if growth_progress < 0.05:
		return plant
	# Plants of one stand spread about +/-10% around the mean culm height.
	var h: float = STEM_HEIGHT * pow(growth_progress, 1.3) * (0.9 + CR.hash_val(seed_val, 98) * 0.2)
	var emergence: float = CR.organ_emergence(repro)
	var fill: float = CR.fill_scale(repro, yield_frac)
	var ripeness: float = smoothstep(0.35, 1.0, repro)
	var panicle_color: Color = CR.ripen_color(
		PANICLE_GREEN, PANICLE_RIPE, PANICLE_DRY, repro, senescence
	)
	# The hill is turned by a random angle per plant.
	var plant_rot: float = CR.hash_val(seed_val, 99) * TAU
	for ti in range(tiller_count(growth_progress)):
		# Hash index block of this tiller: angle, splay, height, spike size,
		# panicle yaw, nod.
		var tb: int = ti * 8
		var tiller_angle: float = plant_rot + float(ti) * TAU / float(NUM_TILLERS)
		tiller_angle += CR.hash_val(seed_val, tb) * 0.5
		var splay: float = 0.03 + CR.hash_val(seed_val, tb + 1) * 0.03
		var base := Vector3(cos(tiller_angle) * splay, 0.0, sin(tiller_angle) * splay)
		# Tillers differ in height (+/-15%): later tillers stay shorter.
		var th: float = h * (0.85 + CR.hash_val(seed_val, tb + 2) * 0.3)
		var r_bot: float = 0.004 * growth_progress + 0.002
		var r_top: float = r_bot * 0.6
		var sheath_top: float = th * (1.0 - PEDUNCLE_FRAC * emergence)
		# Each culm segment owns its material: CR.stamp_wind_frame writes one
		# origin height per material.
		CR.attach_mesh(
			plant,
			CR.create_stem_mesh(sheath_top, r_bot, r_top),
			CR.create_stem_material(senescence, SHEATH_GREEN),
			base + Vector3(0, sheath_top * 0.5, 0)
		)
		if emergence > 0.0:
			var ped_h: float = th - sheath_top
			CR.attach_mesh(
				plant,
				CR.create_stem_mesh(ped_h, r_top, r_top * 0.7),
				CR.create_stem_material(senescence),
				base + Vector3(0, sheath_top + ped_h * 0.5, 0)
			)
		_add_blades(plant, base, th, growth_progress, senescence, stresses, seed_val, ti)
		if emergence > 0.0:
			_add_panicle(plant, base, th, emergence, fill, ripeness, panicle_color, seed_val, ti)
	return plant


static func tiller_count(growth_progress: float) -> int:
	## A seedling is a single main stem; tillers are added through the
	## vegetative phase until the full hill stands by panicle initiation.
	var extra: int = floori(clampf(growth_progress * 1.5, 0.0, 1.0) * float(NUM_TILLERS - 1))
	return 1 + extra


static func _add_blades(
	plant: Node3D,
	base: Vector3,
	th: float,
	growth_progress: float,
	senescence: float,
	stresses: Dictionary,
	seed_val: int,
	ti: int
) -> void:
	## Erect narrow blades along the sheath column, the flag leaf steepest.
	var expansion: float = clampf(growth_progress * 1.3, 0.0, 1.0)
	var droop_bonus: float = CR.stress_droop_bonus(stresses)
	var tiller_rot: float = CR.hash_val(seed_val, ti * 8 + 7) * TAU
	for li in range(NUM_LEAVES):
		# Hash index block of this blade: azimuth, length, node, tilt, droop,
		# twist, sway.
		var lb: int = 100 + ti * 30 + li * 8
		var frac: float = float(li) / float(NUM_LEAVES - 1)
		var node_jitter: float = (CR.hash_val(seed_val, lb + 2) - 0.5) * 0.08
		var y: float = th * (lerpf(0.3, 0.85, frac) + node_jitter)
		var azimuth: float = tiller_rot + float(li % 2) * PI
		azimuth += (CR.hash_val(seed_val, lb) - 0.5) * 0.9
		var len_var: float = 0.85 + CR.hash_val(seed_val, lb + 1) * 0.3
		var leaf_l: float = LEAF_LENGTH * expansion * len_var
		var leaf_h: float = clampf(y / maxf(th, 0.01), 0.0, 1.0)
		var tilt_up: float = lerpf(1.0, 1.3, frac) + (CR.hash_val(seed_val, lb + 3) - 0.5) * 0.24
		tilt_up *= 1.0 - senescence * 0.5 * (1.0 - leaf_h)
		var droop: float = 0.35 - frac * 0.1 + (CR.hash_val(seed_val, lb + 4) - 0.5) * 0.12
		droop += senescence * (1.0 - leaf_h) * 0.35
		var shape := CR.LeafShape.new()
		shape.peak = BLADE_PEAK
		shape.base_frac = BLADE_BASE_FRAC
		shape.keel = BLADE_KEEL
		shape.twist = (CR.hash_val(seed_val, lb + 5) - 0.5) * 1.4
		shape.sway = (CR.hash_val(seed_val, lb + 6) - 0.5) * 0.3
		var pivot := Node3D.new()
		pivot.position = base + Vector3(0, y, 0)
		pivot.rotation.y = azimuth
		CR.attach_mesh(
			pivot,
			CR.build_curved_leaf(
				leaf_l,
				LEAF_WIDTH,
				clampf(droop, 0.0, 1.0),
				CR.leaf_segments,
				0.0,
				BLADE_RISE,
				shape
			),
			CR.create_leaf_material("rice", senescence, stresses, leaf_h),
			Vector3.ZERO,
			Vector3(-tilt_up + droop_bonus * 1.2, 0, 0)
		)
		plant.add_child(pivot)


static func _add_panicle(
	plant: Node3D,
	base: Vector3,
	th: float,
	emergence: float,
	fill: float,
	ripeness: float,
	panicle_color: Color,
	seed_val: int,
	ti: int
) -> void:
	## Spiral panicle at the tiller top: it emerges upright from the flag-leaf
	## sheath and bends over as the grains fill, hanging when ripe. Each
	## panicle swings on its peduncle at its own rhythm in the wind.
	var tb: int = ti * 8
	var pivot := Node3D.new()
	pivot.position = base + Vector3(0, th, 0)
	pivot.rotation.y = CR.hash_val(seed_val, tb + 7) * TAU
	pivot.rotation.x = lerpf(0.15, 0.6, ripeness) * (0.8 + CR.hash_val(seed_val, tb + 5) * 0.4)
	var length: float = (
		PANICLE_LENGTH * emergence * fill * (0.9 + CR.hash_val(seed_val, tb + 6) * 0.2)
	)
	var panicle := Organs.build_spike(
		length,
		PANICLE_WIDTH * fill,
		SPIKELETS,
		0.0,
		lerpf(PANICLE_BEND_GREEN, PANICLE_BEND_RIPE, ripeness),
		true,
		seed_val + ti
	)
	var panicle_mat := CR.create_organ_material(
		panicle_color, 0.75, 1.0, CR.hash_val(seed_val, tb + 3) * TAU
	)
	CR.attach_mesh(pivot, panicle, panicle_mat, Vector3.ZERO)
	plant.add_child(pivot)
