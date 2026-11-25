class_name SoilFaceColour
extends RefCounted
## What the diorama slab's soil faces draw (#646, ADR-022 decision 1), pure and
## static so GUT pins every number the face shader samples.
##
## Per layer: Munsell value from organic matter and texture, moist and dry
## (FAO 2006, Table 46), moved from moist to dry by theta (FAO 2006, Table 57),
## turned into luminous reflectance by ASTM D1535, and applied as the scale of
## the texture class's cross-section texture. Per depth: the engine's
## exponential root density. Hue and chroma come from the textures (a style
## choice); lightness comes from the literature.

## OM = SOC / 0.58, van Bemmelen: the engine's own _VAN_BEMMELEN
## (agrogame/soil/som/pools.py). FAO (2006) gives OC:OM as about 1:1.7 to 2.
const VAN_BEMMELEN := 0.58

## FAO (2006) Guidelines for Soil Description, 4th ed., Table 46, p. 43, after
## Schlichting, Blume & Stahr (1995): Munsell value against organic matter (%),
## per texture column S (sand), L (LS, SL, L) and C (SiL ... C). Rows are
## [value, OM low, OM high]; a low of 0 is an open "<high" class and a high of
## 0 an open ">low" class.
const MOIST := [
	[
		[5.0, 0.0, 0.3],
		[4.5, 0.3, 0.6],
		[4.0, 0.6, 0.9],
		[3.5, 0.9, 1.5],
		[3.0, 1.5, 3.0],
		[2.5, 3.0, 6.0],
		[2.0, 6.0, 0.0]
	],
	[
		[5.0, 0.0, 0.4],
		[4.5, 0.4, 0.6],
		[4.0, 0.6, 1.0],
		[3.5, 1.0, 2.0],
		[3.0, 2.0, 4.0],
		[2.5, 4.0, 0.0]
	],
	[
		[5.5, 0.0, 0.3],
		[5.0, 0.3, 0.6],
		[4.5, 0.6, 0.9],
		[4.0, 0.9, 1.5],
		[3.5, 1.5, 3.0],
		[3.0, 3.0, 5.0],
		[2.5, 5.0, 0.0]
	],
]
const DRY := [
	[
		[7.0, 0.0, 0.3],
		[6.5, 0.3, 0.6],
		[6.0, 0.6, 1.0],
		[5.5, 1.0, 1.5],
		[5.0, 1.5, 2.0],
		[4.5, 2.0, 3.0],
		[4.0, 3.0, 5.0],
		[3.5, 5.0, 8.0],
		[3.0, 8.0, 12.0],
		[2.5, 12.0, 0.0]
	],
	[
		[7.0, 0.0, 0.5],
		[6.5, 0.5, 0.8],
		[6.0, 0.8, 1.2],
		[5.5, 1.2, 2.0],
		[5.0, 2.0, 4.0],
		[4.5, 4.0, 6.0],
		[4.0, 6.0, 9.0],
		[3.5, 9.0, 15.0],
		[3.0, 15.0, 0.0]
	],
	[
		[7.0, 0.0, 0.6],
		[6.5, 0.6, 1.2],
		[6.0, 1.2, 2.0],
		[5.5, 2.0, 3.0],
		[5.0, 3.0, 4.0],
		[4.5, 4.0, 6.0],
		[4.0, 6.0, 9.0],
		[3.5, 9.0, 15.0],
		[3.0, 15.0, 0.0]
	],
]
## FAO (2006) Table 57, p. 50: moistening darkens a "very dry" soil (pF 5)
## fully and a "moist" one (pF 2) not at all. Read linearly in pF with field
## capacity at pF 2 and wilting point at pF 4.2, the dry share at WP is this.
const SHARE_AT_WP := (4.2 - 2.0) / (5.0 - 2.0)
## Cross-section textures per column (S, L, C), and their mean linear
## luminance, measured on the PNGs (sRGB decoded, Rec. 709 weights).
const CROSS_TEXTURES: Array[String] = [
	"res://assets/textures/soil_sandy_cross_albedo.png",
	"res://assets/textures/soil_loam_cross_albedo.png",
	"res://assets/textures/soil_clay_cross_albedo.png",
]
const CROSS_MEAN_Y: Array[float] = [0.462, 0.122, 0.147]
## Style constants (#646): samples per cm of the per-depth profile, and the
## horizon seam's half-width and darkening.
const SAMPLES_PER_CM := 2.0
const SEAM_HALF_CM := 1.5
const SEAM_DARKEN := 0.35
## The per-layer keys of soil_state the faces need (#646).
const PROFILE_KEYS: Array[String] = [
	"water_theta", "layer_thickness_cm", "field_capacity", "wilting_point", "texture", "soc_pct"
]


## Table 46 column of a SoilTexture: 0 for sand, 2 for clay_loam and clay, and
## 1 for sandy_loam, loam and peat.
static func column(texture: String) -> int:
	if texture == "sand":
		return 0
	if texture in ["clay_loam", "clay"]:
		return 2
	return 1


## Geometric midpoint of a Table 46 class; an open class spans a factor of 2.
static func _class_mid(row: Array) -> float:
	var lo: float = row[1]
	var hi: float = row[2]
	if lo <= 0.0:
		lo = hi / 2.0
	if hi <= 0.0:
		hi = lo * 2.0
	return sqrt(lo * hi)


## Munsell value at `om_pct` for a column's rows: linear in ln(OM) between the
## classes' midpoints (logarithmic, as value against SOC is in Konen et al.
## 2003 and Wills et al. 2007), clamped beyond the end classes.
static func value_for(om_pct: float, rows: Array) -> float:
	var x := log(maxf(om_pct, 1e-6))
	var prev: Array = rows[0]
	if x <= log(_class_mid(prev)):
		return prev[0]
	for i in range(1, rows.size()):
		var row: Array = rows[i]
		var xa := log(_class_mid(prev))
		var xb := log(_class_mid(row))
		if x <= xb:
			return lerpf(prev[0], row[0], (x - xa) / (xb - xa))
		prev = row
	return prev[0]


static func moist_value(om_pct: float, texture: String) -> float:
	return value_for(om_pct, MOIST[column(texture)])


static func dry_value(om_pct: float, texture: String) -> float:
	return value_for(om_pct, DRY[column(texture)])


## Share of the moist-to-dry value change at `theta` (FAO 2006 Table 57, read
## linearly in pF): 0 at field capacity and above, SHARE_AT_WP at the wilting
## point, 1 when dry. Linear in theta between the anchors (a style choice).
static func dry_share(theta: float, fc: float, wp: float) -> float:
	if theta >= fc:
		return 0.0
	if theta >= wp:
		return SHARE_AT_WP * (fc - theta) / maxf(fc - wp, 1e-6)
	return SHARE_AT_WP + (1.0 - SHARE_AT_WP) * (wp - theta) / maxf(wp, 1e-6)


## ASTM D1535: luminous reflectance Y (%) of Munsell value `v`, relative to
## the perfect diffuser.
static func luminance(v: float) -> float:
	return v * (1.1914 + v * (-0.22533 + v * (0.23352 + v * (-0.020484 + v * 0.00081939))))


## Luminous reflectance Y (%) of a layer.
static func reflectance(
	soc_pct: float, texture: String, theta: float, fc: float, wp: float
) -> float:
	var om := soc_pct / VAN_BEMMELEN
	var vm := moist_value(om, texture)
	var v := vm + dry_share(theta, fc, wp) * (dry_value(om, texture) - vm)
	return luminance(v)


## Root density at depth `z_cm` for a rooting front at `root_depth_cm`:
## exp(-z / (0.5 D)) on [0, D], else 0. The engine's own kernel
## (RootModule._exponential_distribution, RootParams.kernel_scale_fraction =
## 0.5), after Gerwitz & Page (1974) and Jackson et al. (1996).
static func root_density(z_cm: float, root_depth_cm: float) -> float:
	if root_depth_cm <= 0.0 or z_cm < 0.0 or z_cm > root_depth_cm:
		return 0.0
	return exp(-z_cm / (0.5 * root_depth_cm))


## True when `soil` carries every per-layer key, all of one non-zero length.
static func has_profile(soil: Dictionary) -> bool:
	for key: String in PROFILE_KEYS:
		var values: Variant = soil.get(key)
		if not values is Array or (values as Array).is_empty():
			return false
		if (values as Array).size() != (soil["water_theta"] as Array).size():
			return false
	return true


static func profile_depth_cm(soil: Dictionary) -> float:
	var total := 0.0
	for t: float in soil["layer_thickness_cm"]:
		total += t
	return total


## Albedo scale of layer `i`: (Y / 100) over its cross texture's mean luminance.
static func layer_scale(soil: Dictionary, i: int) -> float:
	var texture: String = soil["texture"][i]
	var y := reflectance(
		soil["soc_pct"][i],
		texture,
		soil["water_theta"][i],
		soil["field_capacity"][i],
		soil["wilting_point"][i]
	)
	return y / 100.0 / CROSS_MEAN_Y[column(texture)]


## The per-depth profile a face samples, over a section `section_cm` deep, one
## sample per 1 / SAMPLES_PER_CM cm: r the albedo scale (darkened on a seam),
## g the root density, b the column / 2. The bottom layer extends to the
## section's bottom; seams mark the horizon boundaries and the section bottom.
static func samples(soil: Dictionary, root_depth_cm: float, section_cm: float) -> PackedColorArray:
	var layers: Array = soil["layer_thickness_cm"]
	var seams: Array[float] = [section_cm - SEAM_HALF_CM]
	var bottom := 0.0
	for i in range(layers.size() - 1):
		bottom += layers[i]
		seams.append(bottom)
	var out := PackedColorArray()
	var li := 0
	bottom = layers[0]
	for p in range(ceili(section_cm * SAMPLES_PER_CM)):
		var z := (p + 0.5) / SAMPLES_PER_CM
		while z > bottom and li < layers.size() - 1:
			li += 1
			bottom += layers[li]
		var r := layer_scale(soil, li)
		for s: float in seams:
			if absf(z - s) < SEAM_HALF_CM:
				r *= 1.0 - SEAM_DARKEN
				break
		var b := column(soil["texture"][li]) / 2.0
		out.append(Color(r, root_density(z, root_depth_cm), b, 1.0))
	return out
