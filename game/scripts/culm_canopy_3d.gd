extends RefCounted
## Leaf canopy of a tall single-culm grass (maize, sorghum).
## Blades are distichous: alternate nodes face opposite sides of the culm.
## Internodes lengthen up the culm, so nodes crowd near the base. Leaves unfold
## one after another from a whorl of erect, still rolled young leaves at the
## apex, and the visible culm ends inside that whorl until heading pushes the
## inflorescence out and the last internodes stretch. Expanded blades are
## keeled and twisted, widest a third of the way out; short blades stand
## erect while long ones arch over under their own weight, and senescing
## lower blades lose turgor and sag first.

const CR = preload("res://scripts/crop_renderer_3d.gd")

## Blade posture follows blade size. A blade shorter than SAG_SIZE_MIN of the
## largest leaf stands near erect at ERECT_TILT with ERECT_DROOP_FRAC of its
## species' droop; it sags to the species' insertion angle and droop once it
## reaches SAG_SIZE_FULL. So a young plant's short leaves point up and only
## the long mid-canopy blades hang over.
const SAG_SIZE_MIN := 0.25
const SAG_SIZE_FULL := 0.85
const ERECT_TILT := 1.2
const ERECT_DROOP_FRAC := 0.3


class Params:
	## Species geometry: sizes in metres, angles in radians.
	var crop_key: String = "maize"
	var max_leaves: int = 12
	## Blade dimensions of the largest leaf.
	var leaf_length: float = 0.9
	var leaf_width: float = 0.1
	## Blade outline: position of maximum width and collar width fraction.
	var peak: float = 0.32
	var base_frac: float = 0.55
	## Keel of an expanded blade (edge lift as a fraction of half-width).
	var keel: float = 0.35
	## Arch of the midrib relative to length; blades leave the culm steeply,
	## so the arch is small and the droop term carries the tip down.
	var rise: float = 0.12
	## Blade size relative to the largest leaf, by leaf index fraction: a
	## linear rise from size_min at the lowest leaf to 1 at size_centre, then
	## a parabolic fall with size_falloff, never below size_min.
	var size_centre: float = 0.6
	var size_falloff: float = 2.2
	var size_min: float = 0.2
	## Insertion angle above horizontal of the lowest and top blades once they
	## are long enough to sag (SAG_SIZE_FULL); shorter blades stand near
	## ERECT_TILT whatever their position.
	var tilt_low: float = 0.5
	var tilt_high: float = 1.05
	## Tip droop of the lowest and top sagging blades.
	var droop_low: float = 0.75
	var droop_high: float = 0.45
	## Spread of blade twist (rad at the tip) and sideways sway (fraction of
	## length) across leaves.
	var twist: float = 1.0
	var sway: float = 0.18
	## Node of the top leaf as a fraction of final culm height: above it is
	## the peduncle, which stretches out at heading.
	var top_node_frac: float = 0.86
	## Growth progress at which the last leaf starts to unfold, and the growth
	## progress an individual leaf needs to expand fully.
	var last_leaf_appears: float = 0.8
	var leaf_expansion: float = 0.15


static func node_frac(p: Params, leaf_frac: float) -> float:
	## Node height of the leaf at leaf_frac (0 lowest, 1 top) as a fraction
	## of final culm height.
	return 0.03 + p.top_node_frac * pow(leaf_frac, 1.25)


static func leaf_expansion(p: Params, growth: float, leaf_frac: float) -> float:
	## Fraction of full size reached by the leaf at leaf_frac.
	var appears: float = leaf_frac * p.last_leaf_appears
	return clampf((growth - appears) / p.leaf_expansion, 0.0, 1.0)


static func stalk_frac(p: Params, growth: float) -> float:
	## Visible culm height before heading as a fraction of final height: just
	## above the node of the last fully expanded leaf, inside the whorl.
	var last_expanded: float = clampf((growth - p.leaf_expansion) / p.last_leaf_appears, 0.0, 1.0)
	return node_frac(p, last_expanded) + 0.05


static func blade_size(p: Params, leaf_frac: float) -> float:
	## Blade length of the leaf at leaf_frac (0 lowest, 1 top) relative to
	## the largest leaf.
	if leaf_frac < p.size_centre:
		return lerpf(p.size_min, 1.0, leaf_frac / maxf(p.size_centre, 0.001))
	var fall: float = 1.0 - p.size_falloff * pow(leaf_frac - p.size_centre, 2.0)
	return clampf(fall, p.size_min, 1.0)


static func sag_weight(size_frac: float) -> float:
	## How far a blade of size_frac (of the largest leaf) has gone from the
	## erect posture of a small blade to the sag of a full-sized one.
	return smoothstep(SAG_SIZE_MIN, SAG_SIZE_FULL, size_frac)


static func add_leaves(
	plant: Node3D,
	p: Params,
	stem_h: float,
	stalk_top: float,
	growth: float,
	emergence: float,
	senescence: float,
	stresses: Dictionary,
	seed_val: int,
	r_bot: float
) -> void:
	## Attach every leaf that has appeared by growth to plant. stem_h is the
	## final culm height the node ladder scales to; blades never attach above
	## stalk_top, the culm height actually drawn. Heading (emergence > 0)
	## unfolds the whole canopy whatever growth says.
	var segs: int = CR.leaf_segments
	var droop_bonus: float = CR.stress_droop_bonus(stresses)
	var plant_rotation: float = CR.hash_val(seed_val, 0) * TAU
	for li in range(p.max_leaves):
		var frac: float = float(li) / float(p.max_leaves - 1)
		var expansion: float = maxf(leaf_expansion(p, growth, frac), emergence)
		if expansion <= 0.0:
			continue
		# Hash index block of this leaf: length, azimuth, droop, node, tilt,
		# width, twist, sway.
		var hi: int = li * 8
		var node_jitter: float = (CR.hash_val(seed_val, hi + 3) - 0.5) * 0.03
		var y: float = minf(stem_h * (node_frac(p, frac) + node_jitter), stalk_top)
		var size_curve: float = blade_size(p, frac)
		var len_var: float = 1.0 + (CR.hash_val(seed_val, hi) - 0.5) * 0.24
		var leaf_len: float = p.leaf_length * size_curve * len_var * expansion
		if leaf_len < 0.01:
			continue
		# Posture follows the blade's actual size: a short blade stands erect,
		# a long one sags to the species' insertion angle and droop.
		var sag: float = sag_weight(size_curve * len_var * expansion)
		# A young blade is still rolled: narrow and strongly keeled.
		var leaf_w: float = p.leaf_width * (0.5 + 0.5 * size_curve) * lerpf(0.35, 1.0, expansion)
		leaf_w *= 0.9 + CR.hash_val(seed_val, hi + 5) * 0.2
		var azimuth: float = plant_rotation + float(li % 2) * PI
		azimuth += (CR.hash_val(seed_val, hi + 1) - 0.5) * 0.6
		var leaf_h: float = clampf(y / maxf(stem_h, 0.01), 0.0, 1.0)
		var tilt_final: float = lerpf(ERECT_TILT, lerpf(p.tilt_low, p.tilt_high, frac), sag)
		tilt_final += (CR.hash_val(seed_val, hi + 4) - 0.5) * 0.3
		var tilt_up: float = lerpf(1.4, tilt_final, smoothstep(0.3, 1.0, expansion))
		tilt_up *= 1.0 - senescence * 0.45 * (1.0 - leaf_h)
		var droop_final: float = lerpf(p.droop_low, p.droop_high, frac)
		droop_final += (CR.hash_val(seed_val, hi + 2) - 0.5) * 0.25
		droop_final *= lerpf(ERECT_DROOP_FRAC, 1.0, sag)
		var droop: float = lerpf(0.1, droop_final, expansion)
		droop += senescence * (1.0 - leaf_h) * 0.5
		var shape := CR.LeafShape.new()
		shape.peak = p.peak
		shape.base_frac = p.base_frac
		shape.keel = lerpf(1.0, p.keel, expansion)
		shape.twist = (CR.hash_val(seed_val, hi + 6) - 0.5) * p.twist
		shape.sway = (CR.hash_val(seed_val, hi + 7) - 0.5) * p.sway
		var pivot := Node3D.new()
		pivot.position = Vector3(0, y, 0)
		pivot.rotation.y = azimuth
		var stem_r_at_y: float = lerpf(r_bot, r_bot * 0.4, leaf_h)
		var leaf_mesh := CR.build_curved_leaf(
			leaf_len, leaf_w, clampf(droop, 0.0, 1.1), segs, stem_r_at_y * 2.0, p.rise, shape
		)
		var leaf_mat := CR.create_leaf_material(p.crop_key, senescence, stresses, leaf_h, expansion)
		CR.attach_mesh(
			pivot, leaf_mesh, leaf_mat, Vector3.ZERO, Vector3(-tilt_up + droop_bonus * 1.2, 0, 0)
		)
		plant.add_child(pivot)
