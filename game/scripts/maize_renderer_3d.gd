extends RefCounted
## Procedural 3D maize renderer.
## A single tapered stalk carrying a distichous canopy of broad, keeled and
## twisted blades (see culm_canopy_3d.gd): leaves unfold from an apical whorl,
## and the stalk ends inside that whorl until the tassel pushes out at heading
## (repro > 0). A husked ear on a short shank sits around mid-stalk; ear and
## tassel size with grain fill and colour as the crop ripens. Senescing lower
## leaves yellow and sag first.

const CR = preload("res://scripts/crop_renderer_3d.gd")
const Canopy = preload("res://scripts/culm_canopy_3d.gd")

const STEM_HEIGHT := 2.5
const STEM_RADIUS_BOTTOM := 0.035
const STEM_RADIUS_TOP := 0.018
const MAX_LEAVES := 12
const EAR_RADIUS := 0.045
const EAR_LENGTH := 0.28
## Ear node as a fraction of stalk height.
const EAR_NODE_FRAC := 0.45
const TASSEL_LENGTH := 0.40
const TASSEL_BRANCHES := 6

const HUSK_GREEN := Color(0.36, 0.56, 0.24)
const HUSK_RIPE := Color(0.78, 0.68, 0.40)
const HUSK_DRY := Color(0.66, 0.54, 0.32)
const SILK_FRESH := Color(0.80, 0.84, 0.50)
const SILK_DRY := Color(0.42, 0.28, 0.16)
const TASSEL_GREEN := Color(0.55, 0.62, 0.30)
const TASSEL_RIPE := Color(0.80, 0.70, 0.40)
const TASSEL_DRY := Color(0.60, 0.48, 0.28)


static func canopy_params() -> Canopy.Params:
	## Maize canopy: a dozen leaves, the largest (around the ear node) 0.9 m
	## by 0.1 m and the top leaf about half that. Long blades leave the stalk
	## at 30 deg above horizontal and arch well over; the short lower and
	## upper ones stand nearly upright.
	var p := Canopy.Params.new()
	p.crop_key = "maize"
	p.max_leaves = MAX_LEAVES
	p.leaf_length = 0.9
	p.leaf_width = 0.10
	p.peak = 0.32
	p.base_frac = 0.55
	p.keel = 0.35
	p.rise = 0.12
	p.size_centre = 0.6
	p.size_falloff = 2.8
	p.size_min = 0.2
	p.tilt_low = 0.5
	p.tilt_high = 1.05
	p.droop_low = 0.75
	p.droop_high = 0.45
	p.twist = 1.0
	p.sway = 0.18
	p.top_node_frac = 0.86
	return p


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
	var g: float = clampf(growth_progress, 0.0, 1.0)
	var p := canopy_params()
	# Stalk elongation is slow while the plant is a whorl of leaves and fast
	# afterwards. Stand heterogeneity: even an evenly emerged stand spreads
	# about +/-12% in plant height around its mean.
	var vigour: float = 1.0 + (CR.hash_val(seed_val, 90) - 0.5) * 0.24
	var h: float = STEM_HEIGHT * pow(g, 1.5) * vigour
	var emergence: float = CR.organ_emergence(repro)
	# Before heading the stalk ends inside the whorl; the top internodes and
	# the tassel peduncle stretch out as the tassel emerges.
	var stalk_top: float = h * lerpf(Canopy.stalk_frac(p, g), 1.0, emergence)
	var r_bot: float = STEM_RADIUS_BOTTOM * g + 0.002
	# Maize stalks taper only slightly; keep a substantial top.
	var r_top: float = maxf(STEM_RADIUS_TOP * g, r_bot * 0.4)
	CR.attach_mesh(
		plant,
		CR.create_stem_mesh(stalk_top, r_bot, r_top),
		CR.create_stem_material(senescence),
		Vector3(0, stalk_top * 0.5, 0)
	)
	Canopy.add_leaves(plant, p, h, stalk_top, g, emergence, senescence, stresses, seed_val, r_bot)
	if repro > 0.0:
		_add_ear(plant, h, r_bot, repro, yield_frac, senescence, seed_val)
		_add_tassel(plant, stalk_top, repro, senescence, seed_val)
	return plant


static func _add_ear(
	plant: Node3D,
	stem_h: float,
	r_bot: float,
	repro: float,
	yield_frac: float,
	senescence: float,
	seed_val: int
) -> void:
	## Husked ear at the ear node with silks at its tip. Small and upright at
	## silking, full size by mid grain fill, tipping outward as the husk dries.
	var emergence: float = CR.organ_emergence(repro)
	var fill: float = CR.fill_scale(repro, yield_frac)
	# Ear size follows plant vigour (+/-10%) on top of grain fill.
	var size_var: float = 0.9 + CR.hash_val(seed_val, 52) * 0.2
	var ear_len: float = EAR_LENGTH * fill * size_var * lerpf(0.5, 1.0, emergence)
	var ear_r: float = EAR_RADIUS * fill * size_var * lerpf(0.6, 1.0, emergence)
	var ripeness: float = smoothstep(0.55, 1.0, repro)
	var side: float = -1.0 if CR.hash_val(seed_val, 50) > 0.5 else 1.0
	# The ear grows from a leaf axil, so it lies in the plant's leaf plane
	# (the blades point along yaw plant_rotation); its node sits a little
	# above or below EAR_NODE_FRAC.
	var yaw: float = CR.hash_val(seed_val, 0) * TAU - PI * 0.5
	yaw += (CR.hash_val(seed_val, 53) - 0.5) * 0.4
	var node_frac: float = EAR_NODE_FRAC + (CR.hash_val(seed_val, 51) - 0.5) * 0.1
	var shank: float = side * r_bot * 0.8
	var pivot := Node3D.new()
	pivot.position = Vector3(shank * cos(yaw), stem_h * node_frac, -shank * sin(yaw))
	# Tilt away from the stalk: upright and hugging it at silking, dropping
	# past horizontal once the husk dries and the shank goes limp. Euler
	# order YXZ applies the z tilt in the plant frame before the yaw.
	pivot.rotation = Vector3(0.0, yaw, -side * lerpf(0.2, 1.75, ripeness))
	plant.add_child(pivot)
	var ear := CapsuleMesh.new()
	ear.radius = ear_r
	ear.height = maxf(ear_len, ear_r * 2.0)
	ear.radial_segments = 8
	ear.rings = 4
	# Ear and silk are centred primitives held fast on the shank: they ride
	# the plant's wind bend without a swing of their own.
	var husk := CR.create_organ_material(
		CR.ripen_color(HUSK_GREEN, HUSK_RIPE, HUSK_DRY, repro, senescence), 0.75, 0.0
	)
	CR.attach_mesh(pivot, ear, husk, Vector3(0, ear.height * 0.5, 0))
	# Silk tuft: pale and fresh at silking, browning within days of pollination.
	var silk := CylinderMesh.new()
	silk.height = 0.08 * emergence
	silk.bottom_radius = ear_r * 0.5
	silk.top_radius = 0.002
	silk.radial_segments = 5
	silk.rings = 1
	var silk_mat := CR.create_organ_material(
		SILK_FRESH.lerp(SILK_DRY, smoothstep(0.1, 0.4, repro)), 0.75, 0.0
	)
	CR.attach_mesh(pivot, silk, silk_mat, Vector3(0, ear.height + silk.height * 0.5, 0))


static func _add_tassel(
	plant: Node3D, stem_h: float, repro: float, senescence: float, seed_val: int
) -> void:
	## Central spike with splayed branches at the apex, unfolding over the
	## first days after heading; pale green at anthesis, straw when dry.
	var tlen: float = TASSEL_LENGTH * CR.organ_emergence(repro)
	tlen *= 0.88 + CR.hash_val(seed_val, 59) * 0.24
	if tlen < 0.02:
		return
	var plant_rotation: float = CR.hash_val(seed_val, 0) * TAU
	# Tassel spikes are centred cylinders: they ride the plant bend only. Each
	# spike owns its material: CR.stamp_wind_frame writes one origin height per
	# material, and the branches sit below the central spike.
	var color: Color = CR.ripen_color(TASSEL_GREEN, TASSEL_RIPE, TASSEL_DRY, repro, senescence)
	for i in range(TASSEL_BRANCHES + 1):
		var is_central: bool = i == 0
		var spike := CylinderMesh.new()
		spike.height = tlen * (1.0 if is_central else 0.65)
		spike.top_radius = 0.0015
		spike.bottom_radius = 0.005
		spike.radial_segments = 4
		spike.rings = 1
		var pivot := Node3D.new()
		pivot.position = Vector3(0, stem_h, 0)
		if not is_central:
			var branch_az: float = plant_rotation + float(i) * TAU / float(TASSEL_BRANCHES)
			pivot.rotation.y = branch_az + CR.hash_val(seed_val, 60 + i) * 0.6
			pivot.rotation.x = 0.55 * (0.8 + CR.hash_val(seed_val, 70 + i) * 0.4)
		CR.attach_mesh(
			pivot,
			spike,
			CR.create_organ_material(color, 0.75, 0.0),
			Vector3(0, spike.height * 0.5, 0)
		)
		plant.add_child(pivot)
