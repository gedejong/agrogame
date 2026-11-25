class_name SoilFaceColour
extends RefCounted
## The soil's colour, for the diorama slab's faces (#646, ADR-022 decision 1)
## and the tiles' tops alike (#680), pure and static so GUT pins every number
## the face and top shaders sample.
##
## Per layer: Munsell value from organic matter and texture, moist and dry
## (FAO 2006, Table 46), moved from moist to dry by theta (FAO 2006, Table 57),
## turned into luminous reflectance by ASTM D1535. Hue and chroma come from a
## cited Munsell notation per soil preset and layer (PRESET_LCH), else from the
## texture. The textures keep only their detail: each is scaled so its mean is
## that colour. The top is the face's top band: same value, same hue. Per
## depth: the engine's exponential root density.

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
## Per column (S, L, C), the mean linear colour of the top albedo texture
## (FarmLayout.SOIL_TEXTURES: sandy, organic, clay) and of the cross texture,
## measured the same way as CROSS_MEAN_Y (#680).
const TOP_MEAN_LINEAR: Array[Vector3] = [
	Vector3(0.6282, 0.4097, 0.2137),
	Vector3(0.1603, 0.0890, 0.0343),
	Vector3(0.2903, 0.2403, 0.1905)
]
const CROSS_MEAN_LINEAR: Array[Vector3] = [
	Vector3(0.6520, 0.4301, 0.2133),
	Vector3(0.1829, 0.1105, 0.0577),
	Vector3(0.1714, 0.1425, 0.1181)
]
## Per soil preset, one entry per preset layer: the CIELAB chroma C*ab and hue
## angle h_ab (degrees; D65) of a cited Munsell notation (#680). hue_at() keeps
## both and takes L* from the layer's own reflectance(), so value stays with the
## cited mapping and hue and chroma with the notation; layers past an entry's
## end use the texture hue. Munsell chroma steps are near-uniform CIELAB chroma
## steps across value: against the renotation, holding C*ab and h_ab is within
## 2.1 dE00 from value 3 to 7 for every entry here, where a fixed chromaticity
## would be off by up to 8.6 (measured for #680). Converted with colour-science
## 0.4.7: Munsell renotation (Newhall, Nickerson & Judd 1943), Illuminant C to
## D65 by CAT02, CIELAB (CIE 15:2004). Each preset layer takes the horizon that
## covers most of it.
const PRESET_LCH := {
	# van Oosten (1971), Sterk lemige dekzandgronden in westelijk Noordbrabant,
	# Boor en Spade (Stiboka), edepot.wur.nl/110272: 44 slightly or non-loamy
	# coversand topsoils, moist, 10YR 3/1.5-2 ("zeer donker grijsbruin") -> 10YR
	# 3/2; their humuspodzol B horizons mostly 7.5YR, chroma 3 or 4 -> 7.5YR 4/4
	# (no value given: 4 assumed). Nothing cited below the B: the texture hue.
	"sandy_temperate": [Vector2(12.75, 72.58), Vector2(25.82, 65.57)],
	# ISRIC reference profile NL 5, Sittard loess Luvisol (Creutzberg), KU Leuven
	# WRB 1998 lecture notes set 9 (luv_prof.pdf), moist: Ap 0-21 10YR 4/3,
	# AB 26-46 10YR 4/4, Bt2 65-95 7.5YR 4/3.
	"loam_temperate": [Vector2(20.14, 74.19), Vector2(26.91, 74.48), Vector2(19.29, 64.49)],
	# Stichting voor Bodemkartering (1964), Bodemkaart van Nederland 1:50 000,
	# toelichting blad 43 West (Willemstad), unit Mn35A example profile
	# (Overflakkee, analysis 11c), moisture not stated: Ap 0-25 2.5Y 4/2,
	# C2g 25-75 5Y 5/2, C2G 75-130 5Y 6/1.
	"clay_temperate": [Vector2(14.21, 84.10), Vector2(14.43, 94.38), Vector2(7.56, 95.80)],
	# The same Dutch marine clay profile: the NL wheat scenarios' soil.
	"clay_netherlands": [Vector2(14.21, 84.10), Vector2(14.43, 94.38), Vector2(7.56, 95.80)],
	# El-Swaify, Walker & Virmani (1984), Dryland management alternatives and
	# research needs for Alfisols in the semi-arid tropics, ICRISAT RA-0073,
	# Appendix B: Psammentic Paleustalf at the ICRISAT Sahelian Center, Sadore,
	# moist: A1 0-17 5YR 5/6, Bt1 32-59 2.5YR 4/6, Bt2 59-85 and Bt3 85-126
	# 2.5YR 4/8.
	"sandy_subsaharan": [Vector2(35.74, 60.13), Vector2(34.26, 49.76), Vector2(45.59, 51.45)],
	# Kenya runs loam_temperate, so its hue is keyed by climate, for display
	# only (Edwin, 2026-11-25), until #684 gives it a Nitisol preset and the
	# hue a soil key. KE 1 Nitisol 7 km W of Nairobi under maize (Rachilo &
	# Michieka, KSS), WRB 1998 lecture notes set 6 (nit_prof.pdf), moist:
	# Ah 0-18 5YR 3/3, AB 18-37 to Bt2 66-116 2.5YR 3/4.
	"loam_temperate@kenya_highlands":
	[Vector2(17.95, 54.27), Vector2(23.33, 46.20), Vector2(23.33, 46.20)],
}
## CIE 15:2004: the D65 white (2 degree observer) and the CIELAB breakpoint 6/29.
const D65_WHITE := Vector3(0.95047, 1.0, 1.08883)
const LAB_DELTA := 6.0 / 29.0
## Rec. 709 luminance weights (ITU-R BT.709), as for CROSS_MEAN_Y.
const REC709 := Vector3(0.2126, 0.7152, 0.0722)
## Mean over a tile of soil_tile.gdshader's coarse-grain, fine-grain and crack
## factors, computed numerically from its noise for #680 (the GUT test re-derives
## it), so a top's mean albedo is its surface_albedo().
const TOP_GRAIN_MEAN := 0.768
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


## Hue of column `col` at unit luminance: its top texture's mean colour over
## that colour's Rec. 709 luminance (#680).
static func hue(col: int) -> Vector3:
	var m: Vector3 = TOP_MEAN_LINEAR[col]
	return m / m.dot(REC709)


## Hue of layer `layer` of soil preset `key` at luminous reflectance `y` (0-1)
## (#680): the preset's cited hue and chroma at that lightness, else its
## column's texture hue.
static func layer_hue(key: String, layer: int, col: int, y: float) -> Vector3:
	if PRESET_LCH.has(key):
		var lch: Array = PRESET_LCH[key]
		if layer < lch.size():
			return hue_at(lab_lightness(y), lch[layer])
	return hue(col)


## The PRESET_LCH key of a tile (#680): "<soil>@<climate>" when that has its
## own entry, else the soil preset key.
static func colour_key(tile: Dictionary) -> String:
	var soil: String = tile.get("soil_profile_key", "")
	var keyed := "%s@%s" % [soil, tile.get("climate_key", "")]
	return keyed if PRESET_LCH.has(keyed) else soil


## CIELAB L* of luminous reflectance `y` (0-1) (CIE 15:2004).
static func lab_lightness(y: float) -> float:
	var f := (
		pow(y, 1.0 / 3.0)
		if y > pow(LAB_DELTA, 3.0)
		else y / (3.0 * LAB_DELTA * LAB_DELTA) + 4.0 / 29.0
	)
	return 116.0 * f - 16.0


## Linear sRGB at unit Rec. 709 luminance of CIELAB (`l_star`, C*ab, h_ab) under
## D65: CIELAB to XYZ by CIE 15:2004, XYZ to linear sRGB by IEC 61966-2-1.
## Channels below 0 (out of gamut) clamp to 0.
static func hue_at(l_star: float, lch: Vector2) -> Vector3:
	var fy := (l_star + 16.0) / 116.0
	var h := deg_to_rad(lch.y)
	var xyz := Vector3(
		D65_WHITE.x * _lab_inverse(fy + lch.x * cos(h) / 500.0),
		_lab_inverse(fy),
		D65_WHITE.z * _lab_inverse(fy - lch.x * sin(h) / 200.0)
	)
	var rgb := Vector3(
		3.2406 * xyz.x - 1.5372 * xyz.y - 0.4986 * xyz.z,
		-0.9689 * xyz.x + 1.8758 * xyz.y + 0.0415 * xyz.z,
		0.0557 * xyz.x - 0.2040 * xyz.y + 1.0570 * xyz.z
	)
	rgb = rgb.max(Vector3.ZERO)
	return rgb / rgb.dot(REC709)


static func _lab_inverse(f: float) -> float:
	return f * f * f if f > LAB_DELTA else 3.0 * LAB_DELTA * LAB_DELTA * (f - 4.0 / 29.0)


## Per-channel gain that gives layer `i`'s cross texture the hue of `soil`'s
## layer `i`, of preset `key`, at unchanged luminance (#680).
static func face_gain(soil: Dictionary, key: String, i: int) -> Vector3:
	var col := column(soil["texture"][i])
	var c: Vector3 = CROSS_MEAN_LINEAR[col]
	# Over CROSS_MEAN_Y, as layer_scale(), so the face's mean is hue x Y exactly.
	return layer_hue(key, i, col, layer_y(soil, i)) / (c / CROSS_MEAN_Y[col])


## The per-depth hue gains a face samples, laid out as samples() (#680).
static func hue_samples(soil: Dictionary, key: String, section_cm: float) -> PackedColorArray:
	var layers: Array = soil["layer_thickness_cm"]
	var out := PackedColorArray()
	var li := 0
	var bottom: float = layers[0]
	for p in range(ceili(section_cm * SAMPLES_PER_CM)):
		var z := (p + 0.5) / SAMPLES_PER_CM
		while z > bottom and li < layers.size() - 1:
			li += 1
			bottom += layers[li]
		var g := face_gain(soil, key, li)
		out.append(Color(g.x, g.y, g.z, 1.0))
	return out


## Linear albedo of the soil surface: the top layer's reflectance (the face's
## top band, same Munsell value) in its hue (#680).
static func surface_albedo(soil: Dictionary, key: String = "") -> Vector3:
	var y := layer_y(soil, 0)
	return layer_hue(key, 0, column(soil["texture"][0]), y) * y


## Per-channel gain that turns the top texture of column `top_col` into
## `albedo` on average, grain included (#680).
static func top_gain(albedo: Vector3, top_col: int) -> Vector3:
	return albedo / (TOP_MEAN_LINEAR[top_col] * TOP_GRAIN_MEAN)


## Degree of saturation of the top layer, theta over porosity (Hillel 2004,
## Introduction to Environmental Soil Physics, ch. 2): what wets the top's gloss
## (#680, replacing an uncited saturated theta of 0.45). 0 without porosity.
static func saturation(soil: Dictionary) -> float:
	var porosity: Array = soil.get("porosity", [])
	if porosity.is_empty() or porosity[0] <= 0.0:
		return 0.0
	return clampf(soil["water_theta"][0] / porosity[0], 0.0, 1.0)


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


## Luminous reflectance (0-1) of `soil`'s layer `i`.
static func layer_y(soil: Dictionary, i: int) -> float:
	return (
		reflectance(
			soil["soc_pct"][i],
			soil["texture"][i],
			soil["water_theta"][i],
			soil["field_capacity"][i],
			soil["wilting_point"][i]
		)
		/ 100.0
	)


## Albedo scale of layer `i`: (Y / 100) over its cross texture's mean luminance.
static func layer_scale(soil: Dictionary, i: int) -> float:
	return layer_y(soil, i) / CROSS_MEAN_Y[column(soil["texture"][i])]


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
