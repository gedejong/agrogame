extends RefCounted
## Procedural 3D wheat renderer.
## A plant is a few tillers from one crown. Each tiller is a sheath column
## (the visible green "stem") with narrow keeled blades: the lower ones arch
## down under their own weight, the flag leaf at the top stands erect. Once
## headed (repro > 0) an exserted peduncle carries an awned spike of
## alternating spikelets: green at anthesis, golden through grain fill,
## nodding as it dries.

const CR = preload("res://scripts/crop_renderer_3d.gd")
const Organs = preload("res://scripts/crop_organ_meshes.gd")

const NUM_TILLERS := 4
const STEM_HEIGHT := 0.85
const NUM_LEAVES := 4
const LEAF_WIDTH := 0.02
const LEAF_LENGTH := 0.24
## Arch height of a blade relative to its length: cereal blades stand
## nearly straight and bend outward only towards the tip.
const BLADE_RISE := 0.08
## Blade outline: widest a third of the way out and broad at the collar,
## with a keel that flattens towards the tip.
const BLADE_PEAK := 0.35
const BLADE_BASE_FRAC := 0.75
const BLADE_KEEL := 0.3
const SPIKE_LENGTH := 0.105
const SPIKE_WIDTH := 0.02
const SPIKELETS := 10
const AWN_LENGTH := 0.05
## Fraction of tiller height exposed as bare peduncle after heading.
const PEDUNCLE_FRAC := 0.25
## Maximum nod of a ripe head (rad) at the peduncle top, and the bend of the
## head itself.
const NOD_MAX := 0.5
const HEAD_BEND_MAX := 0.35

const SPIKE_GREEN := Color(0.45, 0.60, 0.28)
const SPIKE_RIPE := Color(0.86, 0.72, 0.36)
const SPIKE_DRY := Color(0.74, 0.60, 0.32)
## The sheath column is leaf tissue: leaf green, drying to straw.
const SHEATH_GREEN := Color(0.24, 0.52, 0.20)


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
	# Culm elongation: mostly during stem extension, complete by heading.
	# Plants of one stand spread about +/-10% around the mean culm height.
	var h: float = STEM_HEIGHT * pow(growth_progress, 1.3) * (0.9 + CR.hash_val(seed_val, 98) * 0.2)
	var emergence: float = CR.organ_emergence(repro)
	var fill: float = CR.fill_scale(repro, yield_frac)
	var ripeness: float = smoothstep(0.5, 1.0, repro)
	var spike_color: Color = CR.ripen_color(SPIKE_GREEN, SPIKE_RIPE, SPIKE_DRY, repro, senescence)
	# The tiller fan is turned by a random angle per plant, so neighbouring
	# crowns do not all splay the same way.
	var plant_rot: float = CR.hash_val(seed_val, 99) * TAU
	for ti in range(tiller_count(growth_progress)):
		var tiller_angle: float = plant_rot + float(ti) * TAU / float(NUM_TILLERS)
		tiller_angle += CR.hash_val(seed_val, ti * 10) * 0.5
		var splay: float = 0.03 + CR.hash_val(seed_val, ti * 10 + 1) * 0.03
		var base := Vector3(cos(tiller_angle) * splay, 0.0, sin(tiller_angle) * splay)
		# Tillers differ in height (+/-15%): later tillers stay shorter.
		var th: float = h * (0.85 + CR.hash_val(seed_val, ti * 10 + 2) * 0.3)
		var r_bot: float = 0.005 * growth_progress + 0.002
		var r_top: float = r_bot * 0.5
		# The sheath column reaches the top until heading exposes the peduncle.
		# Each culm segment owns its material: CR.stamp_wind_frame writes one
		# origin height per material.
		var sheath_top: float = th * (1.0 - PEDUNCLE_FRAC * emergence)
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
			_add_spike(plant, base, th, emergence, fill, ripeness, spike_color, seed_val, ti)
	return plant


static func tiller_count(growth_progress: float) -> int:
	## A seedling is a single main stem; tillers are added through the
	## vegetative phase until the full complement stands by stem extension.
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
	## Blades along the sheath column: lower blades arch outward and down,
	## the flag leaf at the top stands nearly erect.
	var expansion: float = clampf(growth_progress * 1.3, 0.0, 1.0)
	var droop_bonus: float = CR.stress_droop_bonus(stresses)
	var tiller_rot: float = CR.hash_val(seed_val, ti * 10 + 7) * TAU
	for li in range(NUM_LEAVES):
		# Hash index block of this blade: azimuth, length, node, tilt, droop,
		# twist, sway.
		var lb: int = 100 + ti * 40 + li * 8
		var frac: float = float(li) / float(NUM_LEAVES - 1)
		var is_flag: bool = li == NUM_LEAVES - 1
		var node_jitter: float = (CR.hash_val(seed_val, lb + 2) - 0.5) * 0.08
		var y: float = th * (lerpf(0.25, 0.85, frac) + node_jitter)
		# Alternate sides (distichous) with a little scatter.
		var azimuth: float = tiller_rot + float(li % 2) * PI
		azimuth += (CR.hash_val(seed_val, lb) - 0.5) * 0.9
		var len_var: float = 0.85 + CR.hash_val(seed_val, lb + 1) * 0.3
		var leaf_l: float = LEAF_LENGTH * expansion * len_var * (0.8 if is_flag else 1.0)
		var leaf_h: float = clampf(y / maxf(th, 0.01), 0.0, 1.0)
		var tilt_up: float = 1.2 if is_flag else lerpf(0.8, 1.05, frac)
		tilt_up += (CR.hash_val(seed_val, lb + 3) - 0.5) * 0.24
		tilt_up *= 1.0 - senescence * 0.5 * (1.0 - leaf_h)
		var droop: float = 0.3 if is_flag else 0.65 - frac * 0.25
		droop += (CR.hash_val(seed_val, lb + 4) - 0.5) * 0.12
		droop += senescence * (1.0 - leaf_h) * 0.35
		var shape := CR.LeafShape.new()
		shape.peak = BLADE_PEAK
		shape.base_frac = BLADE_BASE_FRAC
		shape.keel = BLADE_KEEL
		shape.twist = (CR.hash_val(seed_val, lb + 5) - 0.5) * 1.2
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
			CR.create_leaf_material("wheat", senescence, stresses, leaf_h),
			Vector3.ZERO,
			Vector3(-tilt_up + droop_bonus * 1.2, 0, 0)
		)
		plant.add_child(pivot)


static func _add_spike(
	plant: Node3D,
	base: Vector3,
	th: float,
	emergence: float,
	fill: float,
	ripeness: float,
	spike_color: Color,
	seed_val: int,
	ti: int
) -> void:
	## Awned spike at the tiller top: it pushes out of the flag-leaf sheath,
	## reaches full size by anthesis and nods over as the grain dries. Each
	## head swings on its peduncle at its own rhythm in the wind.
	var pivot := Node3D.new()
	pivot.position = base + Vector3(0, th, 0)
	pivot.rotation.y = CR.hash_val(seed_val, ti * 10 + 8) * TAU
	var nod_var: float = 0.7 + CR.hash_val(seed_val, ti * 10 + 9) * 0.6
	pivot.rotation.x = NOD_MAX * ripeness * nod_var
	var spike_len: float = (
		SPIKE_LENGTH * emergence * fill * (0.9 + CR.hash_val(seed_val, ti * 10 + 6) * 0.2)
	)
	var spike := Organs.build_spike(
		spike_len,
		SPIKE_WIDTH * fill,
		SPIKELETS,
		AWN_LENGTH * emergence,
		HEAD_BEND_MAX * ripeness * nod_var,
		false,
		seed_val + ti
	)
	var spike_mat := CR.create_organ_material(
		spike_color, 0.75, 1.0, CR.hash_val(seed_val, ti * 10 + 5) * TAU
	)
	CR.attach_mesh(pivot, spike, spike_mat, Vector3.ZERO)
	plant.add_child(pivot)
