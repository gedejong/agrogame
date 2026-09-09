extends SceneTree
## Generates the leaf alpha masks sampled by the crop leaf shader.
## Grass masks are laid out as the strip UVs of build_curved_leaf: x runs
## collar to tip, y edge to edge with the midrib at the centre. The blade
## outline itself is geometry; the mask only sharpens the tip and frays the
## margins a little. The vine mask is a centred palmate outline for the leaf
## quad: x across the blade, y from the petiole (top) to the apex (bottom).
## Run from the game directory to rewrite the PNGs, then re-import:
##   godot --headless -s scripts/leaf_mask_generator.gd
##   godot --headless --import

const CR = preload("res://scripts/crop_renderer_3d.gd")

const OUT_DIR := "res://assets/textures/"
const GRASS_SIZE := Vector2i(256, 64)
const GRAPE_SIZE := Vector2i(128, 128)
## Per-crop tip taper (fraction of length) and margin waviness (fraction of
## width), with the hash seed of the margin phases.
const GRASS_PARAMS := {
	"maize": {"tip": 0.06, "wave": 0.035, "seed": 1},
	"wheat": {"tip": 0.08, "wave": 0.03, "seed": 2},
	"sorghum": {"tip": 0.06, "wave": 0.035, "seed": 3},
	"rice": {"tip": 0.10, "wave": 0.03, "seed": 4},
}
const GRAPE_SEED := 7
## Lobes of the palmate outline as [angle from the petiole, amplitude,
## angular width]: apex lobe opposite the petiole, two laterals, two basals.
const LOBES := [
	[PI, 1.0, 0.36],
	[0.62 * PI, 0.95, 0.30],
	[-0.62 * PI, 0.95, 0.30],
	[0.27 * PI, 0.72, 0.22],
	[-0.27 * PI, 0.72, 0.22],
]


func _init() -> void:
	write_all(OUT_DIR)
	quit()


static func write_all(dir: String) -> void:
	for key: String in GRASS_PARAMS:
		var p: Dictionary = GRASS_PARAMS[key]
		var img := build_blade_mask(GRASS_SIZE, p["tip"], p["wave"], p["seed"])
		img.save_png(dir + "leaf_%s_alpha.png" % key)
	build_palmate_mask(GRAPE_SIZE, GRAPE_SEED).save_png(dir + "leaf_grape_alpha.png")


static func build_blade_mask(size: Vector2i, tip_frac: float, wave: float, seed_val: int) -> Image:
	## Grass blade: solid across the strip, margins frayed by two sinusoids of
	## different frequency on each edge, tapering to a point over the last
	## tip_frac of the length.
	var img := Image.create(size.x, size.y, false, Image.FORMAT_RGBA8)
	var ph: Array[float] = []
	for i in range(4):
		ph.append(CR.hash_val(seed_val, i) * TAU)
	for px in range(size.x):
		var t: float = (float(px) + 0.5) / float(size.x)
		var taper: float = 1.0
		if t > 1.0 - tip_frac:
			taper = pow((1.0 - t) / tip_frac, 0.7)
		var shrink_a: float = (
			wave * (0.5 + 0.35 * sin(t * TAU * 5.3 + ph[0]) + 0.15 * sin(t * TAU * 13.7 + ph[1]))
		)
		var shrink_b: float = (
			wave * (0.5 + 0.35 * sin(t * TAU * 4.7 + ph[2]) + 0.15 * sin(t * TAU * 12.3 + ph[3]))
		)
		var hw_a: float = 0.5 * taper - shrink_a
		var hw_b: float = 0.5 * taper - shrink_b
		for py in range(size.y):
			var s: float = (float(py) + 0.5) / float(size.y) - 0.5
			var on: bool = s < 0.0 and -s < hw_a or s >= 0.0 and s < hw_b
			img.set_pixel(px, py, Color.WHITE if on else Color(0, 0, 0, 0))
	return img


static func build_palmate_mask(size: Vector2i, seed_val: int) -> Image:
	## Five-lobed vine leaf centred in the square: apex lobe at the bottom,
	## laterals at the sides, small basal lobes flanking the petiolar sinus at
	## the top, and a finely serrated margin.
	var img := Image.create(size.x, size.y, false, Image.FORMAT_RGBA8)
	var centre := Vector2(0.5, 0.5)
	var serration_phase: float = CR.hash_val(seed_val, 0) * TAU
	for py in range(size.y):
		for px in range(size.x):
			var d := Vector2((float(px) + 0.5) / float(size.x), (float(py) + 0.5) / float(size.y))
			d -= centre
			# Angle from the petiole direction (up, -y): 0 at the petiole,
			# +-PI at the apex.
			var theta: float = atan2(d.x, -d.y)
			var r: float = palmate_radius(theta, serration_phase)
			img.set_pixel(px, py, Color.WHITE if d.length() < r else Color(0, 0, 0, 0))
	return img


static func palmate_radius(theta: float, serration_phase: float) -> float:
	## Outline radius (fraction of the texture) of the palmate leaf at angle
	## theta from the petiole.
	var lobes: float = 0.0
	for lobe: Array in LOBES:
		var diff: float = wrapf(theta - lobe[0], -PI, PI) / lobe[2]
		lobes = maxf(lobes, lobe[1] * exp(-diff * diff))
	var r: float = 0.46 * (0.56 + 0.44 * lobes)
	# Petiolar sinus: a deep notch where the petiole joins.
	r *= 1.0 - 0.4 * exp(-pow(theta / 0.17, 2.0))
	r *= 1.0 + 0.02 * sin(theta * 41.0 + serration_phase)
	return r
