class_name DioramaArtefacts
extends RefCounted
## The decorative extension's artefacts (#652, ADR-022 decision 1): corestones
## in the Kenyan saprolite, gravel lenses in the Dutch and Sahel sand, and old
## roots just below the simulated profile. A deterministic generator places
## them from the climate key and a seed, never from a simulation value, and
## writes them to a small data texture for soil_extension.gdshader.

enum Kind { CORESTONE, LENS, ROOT }

## Sizes from the #652 refinement: corestones rounded and 0.2 to 0.8 m across
## (corestones in saprolite: Taylor & Eggleton 2001); lenses 0.5 to 2 m long
## and 0.05 to 0.2 m thick; old roots gone by 2.0 m.
const CORESTONE_DIAMETER_M := Vector2(0.2, 0.8)
const CORESTONE_ASPECT := Vector2(0.75, 1.0)  # height over width: rounded
## Ruxton & Berry (1957), Weathering of granite and associated erosional
## features in Hong Kong, GSA Bulletin 68, 1263-1292: down a weathering profile,
## corestones go from few, small and rounded to many, large and joint-bounded
## (blocky). Here a stone's depth share t in its layer has density 2t, its
## diameter is log-uniform up to a ceiling that rises from this share of the
## log range at the top of the layer to all of it at the base, and its outline
## turns from oval to rounded block with t (style constants within that trend).
const CORESTONE_TOP_SHARE := 0.4
const LENS_LENGTH_M := Vector2(0.5, 2.0)
const LENS_THICKNESS_M := Vector2(0.05, 0.2)
const ROOT_FLOOR_M := 2.0
## Kept clear of a layer boundary: the shader's WAVE_M, its largest excursion.
const BOUNDARY_MARGIN_M := 0.05
## Style constants: counts per m² of host layer, one old root per so many
## metres of face, how far below the profile bottom a root may start, a root's
## width and shortest length, and tries per artefact.
const CORESTONES_PER_M2 := 0.5
const LENSES_PER_M2 := 0.25
const ROOT_SPACING_M := 1.2
const ROOT_START_M := 0.15
const ROOT_WIDTH_M := 0.005
const ROOT_MIN_LENGTH_M := 0.25
const TRIES := 20


## The artefacts under `climate_key` along `u_span_m` (first and last u of the
## unfolded face) between `profile_bottom_m` and `slab_bottom_m`, each a box
## {kind, u, d, half_w, half_h, phase, block} centred at (u, d), in metres;
## block (0 to 1) turns a corestone from oval to rounded block.
static func place(
	climate_key: String,
	seed_value: int,
	profile_bottom_m: float,
	slab_bottom_m: float,
	u_span_m: Vector2
) -> Array[Dictionary]:
	var out: Array[Dictionary] = []
	var layers := DioramaRegions.layers_for(climate_key)
	if layers.is_empty():
		return out
	var rng := RandomNumberGenerator.new()
	rng.seed = hash([climate_key, seed_value])
	for layer: Dictionary in layers:
		var top := maxf(layer["top_m"], profile_bottom_m)
		var bottom := minf(layer["bottom_m"], slab_bottom_m)
		if layer["top_m"] > 0.0:
			top += BOUNDARY_MARGIN_M
		if layer["bottom_m"] < slab_bottom_m:
			bottom -= BOUNDARY_MARGIN_M
		var host := Rect2(u_span_m.x, top, u_span_m.y - u_span_m.x, bottom - top)
		if host.size.y <= 0.0:
			continue
		if layer["artefact"] == "corestone":
			_scatter(out, rng, Kind.CORESTONE, host, CORESTONES_PER_M2)
		elif layer["artefact"] == "lens":
			_scatter(out, rng, Kind.LENS, host, LENSES_PER_M2)
	_roots(out, rng, profile_bottom_m, u_span_m)
	return out


## The placements as an RGBA float texture, one column each: row 0 holds (u,
## d, half_w, half_h), row 1 (kind, phase, block).
static func texture(placed: Array[Dictionary]) -> ImageTexture:
	var img := Image.create(maxi(placed.size(), 1), 2, false, Image.FORMAT_RGBAF)
	for i in range(placed.size()):
		var a: Dictionary = placed[i]
		img.set_pixel(i, 0, Color(a["u"], a["d"], a["half_w"], a["half_h"]))
		img.set_pixel(i, 1, Color(a["kind"], a["phase"], a["block"], 0.0))
	return ImageTexture.create_from_image(img)


## Up to `per_m2` per m² of `host` of `kind`, wholly inside it vertically and
## clear of every body already placed: lenses anywhere in depth, corestones
## more often, larger and blockier towards the base (Ruxton & Berry 1957).
static func _scatter(
	out: Array[Dictionary], rng: RandomNumberGenerator, kind: Kind, host: Rect2, per_m2: float
) -> void:
	for _n in range(roundi(host.get_area() * per_m2)):
		for _try in range(TRIES):
			var half := Vector2.ZERO
			var t := rng.randf()
			if kind == Kind.CORESTONE:
				t = sqrt(t)
				var span := CORESTONE_DIAMETER_M.y / CORESTONE_DIAMETER_M.x
				var share := rng.randf() * lerpf(CORESTONE_TOP_SHARE, 1.0, t)
				half.x = CORESTONE_DIAMETER_M.x * pow(span, share) / 2.0
				half.y = half.x * rng.randf_range(CORESTONE_ASPECT.x, CORESTONE_ASPECT.y)
			else:
				half.x = rng.randf_range(LENS_LENGTH_M.x, LENS_LENGTH_M.y) / 2.0
				half.y = rng.randf_range(LENS_THICKNESS_M.x, LENS_THICKNESS_M.y) / 2.0
			if 2.0 * half.y > host.size.y:
				continue
			var u := rng.randf_range(host.position.x, host.end.x)
			var d := host.position.y + half.y + t * (host.size.y - 2.0 * half.y)
			var box := Rect2(Vector2(u, d) - half, half * 2.0)
			if out.all(func(a: Dictionary) -> bool: return not box.intersects(_box(a))):
				var block := t if kind == Kind.CORESTONE else 0.0
				out.append(_placed(kind, Vector2(u, d), half, rng.randf(), block))
				break


## One old root every ROOT_SPACING_M or so, from just below the profile bottom
## down to at most ROOT_FLOOR_M.
static func _roots(
	out: Array[Dictionary], rng: RandomNumberGenerator, profile_bottom_m: float, u_span_m: Vector2
) -> void:
	for k in range(floori((u_span_m.y - u_span_m.x) / ROOT_SPACING_M)):
		var u := u_span_m.x + (k + rng.randf()) * ROOT_SPACING_M
		var top := profile_bottom_m + rng.randf_range(0.0, ROOT_START_M)
		if ROOT_FLOOR_M - top < ROOT_MIN_LENGTH_M:
			continue
		var half := (
			Vector2(ROOT_WIDTH_M, rng.randf_range(ROOT_MIN_LENGTH_M, ROOT_FLOOR_M - top)) / 2.0
		)
		out.append(_placed(Kind.ROOT, Vector2(u, top + half.y), half, rng.randf(), 0.0))


static func _placed(
	kind: Kind, centre: Vector2, half: Vector2, phase: float, block: float
) -> Dictionary:
	return {
		"kind": kind,
		"u": centre.x,
		"d": centre.y,
		"half_w": half.x,
		"half_h": half.y,
		"phase": phase,
		"block": block,
	}


static func _box(a: Dictionary) -> Rect2:
	var half := Vector2(a["half_w"], a["half_h"])
	return Rect2(Vector2(a["u"], a["d"]) - half, half * 2.0)
