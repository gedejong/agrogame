extends RefCounted
## Procedural 3D grain sorghum renderer.
## A sturdy single culm with a distichous canopy of waxy blue-green blades
## (see culm_canopy_3d.gd), more upright and narrower than maize. After
## heading (repro > 0) an exserted peduncle carries a compact, lumpy panicle
## that fills and colours from green to bronze-red as it ripens. Sorghum is
## stay-green: its leaves keep colour longer than maize does.

const CR = preload("res://scripts/crop_renderer_3d.gd")
const Canopy = preload("res://scripts/culm_canopy_3d.gd")
const Organs = preload("res://scripts/crop_organ_meshes.gd")

const STEM_HEIGHT := 1.6
const STEM_RADIUS := 0.014
const MAX_LEAVES := 10
const HEAD_RADIUS := 0.055
const HEAD_LENGTH := 0.24
## Node of the top leaf as a fraction of culm height; the peduncle above it
## exserts the head at heading.
const TOP_NODE_FRAC := 0.82

## Head colours are set light: the head mesh darkens its facets in vertex
## colour to read as packed grain.
const HEAD_GREEN := Color(0.58, 0.70, 0.36)
const HEAD_RIPE := Color(0.72, 0.36, 0.22)
const HEAD_DRY := Color(0.54, 0.29, 0.17)


static func canopy_params() -> Canopy.Params:
	## Sorghum canopy: ten fairly even blades held more upright than maize,
	## strongly keeled and twisted along their length.
	var p := Canopy.Params.new()
	p.crop_key = "sorghum"
	p.max_leaves = MAX_LEAVES
	p.leaf_length = 0.65
	p.leaf_width = 0.065
	p.peak = 0.35
	p.base_frac = 0.6
	p.keel = 0.45
	p.rise = 0.1
	p.size_centre = 0.55
	p.size_falloff = 1.6
	p.size_min = 0.3
	p.tilt_low = 0.75
	p.tilt_high = 1.15
	p.droop_low = 0.5
	p.droop_high = 0.3
	p.twist = 1.6
	p.sway = 0.3
	p.top_node_frac = TOP_NODE_FRAC
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
	# Plants of one stand spread about +/-12% around the mean culm height.
	var h: float = STEM_HEIGHT * pow(g, 1.5) * (0.88 + CR.hash_val(seed_val, 90) * 0.24)
	var emergence: float = CR.organ_emergence(repro)
	var fill: float = CR.fill_scale(repro, yield_frac)
	# The culm ends inside the whorl until heading exserts the peduncle.
	var culm_top: float = h * lerpf(Canopy.stalk_frac(p, g), 1.0, emergence)
	var r: float = STEM_RADIUS * g + 0.003
	CR.attach_mesh(
		plant,
		CR.create_stem_mesh(culm_top, r, r * 0.6),
		CR.create_stem_material(senescence),
		Vector3(0, culm_top * 0.5, 0)
	)
	Canopy.add_leaves(plant, p, h, culm_top, g, emergence, senescence, stresses, seed_val, r)
	if emergence > 0.0:
		# Head size follows plant vigour (+/-10%) on top of grain fill.
		var head_var: float = 0.9 + CR.hash_val(seed_val, 91) * 0.2
		_add_head(plant, culm_top, emergence, fill * head_var, repro, senescence, seed_val)
	return plant


static func _add_head(
	plant: Node3D,
	top: float,
	emergence: float,
	fill: float,
	repro: float,
	senescence: float,
	seed_val: int
) -> void:
	## Compact panicle on the peduncle tip: it pushes out of the flag-leaf
	## sheath, then fills and colours. The stout peduncle lets it swing only
	## a little in the wind.
	var head := Organs.build_panicle_head(
		HEAD_LENGTH * fill * emergence, HEAD_RADIUS * fill * lerpf(0.5, 1.0, emergence), seed_val
	)
	var head_mat := CR.create_organ_material(
		CR.ripen_color(HEAD_GREEN, HEAD_RIPE, HEAD_DRY, repro, senescence),
		0.75,
		0.6,
		CR.hash_val(seed_val, 92) * TAU
	)
	CR.attach_mesh(plant, head, head_mat, Vector3(0, top, 0))
