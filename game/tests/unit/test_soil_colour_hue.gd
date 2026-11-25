extends GutTest
## SoilFaceColour's colour (#680): one cited colour for the tops and the faces,
## with value from the cited mapping and a Munsell hue and chroma per preset.

## Per PRESET_LCH entry and layer: the cited notation's CIELAB L* and its linear
## sRGB at unit luminance, from colour-science 0.4.7 (Munsell renotation,
## Illuminant C to D65 by CAT02), computed for #680.
const MUNSELL := {
	"sandy_temperate":
	[[30.406, Vector3(1.3915, 0.9287, 0.5538)], [40.776, Vector3(1.7256, 0.8488, 0.3612)]],
	"loam_temperate":
	[
		[40.779, Vector3(1.4746, 0.9148, 0.4464)],
		[40.788, Vector3(1.6069, 0.8891, 0.3111)],
		[40.768, Vector3(1.5656, 0.8829, 0.4941)]
	],
	"clay_temperate":
	[
		[40.775, Vector3(1.2583, 0.9666, 0.5708)],
		[51.049, Vector3(1.1433, 0.9957, 0.6209)],
		[61.072, Vector3(1.0657, 0.9991, 0.8151)]
	],
	"sandy_subsaharan":
	[
		[51.045, Vector3(1.9347, 0.7917, 0.3107)],
		[40.755, Vector3(2.2428, 0.6995, 0.3175)],
		[40.755, Vector3(2.6058, 0.6069, 0.1652)]
	],
	"loam_temperate@kenya_highlands":
	[
		[30.397, Vector3(1.7557, 0.8271, 0.4875)],
		[30.389, Vector3(2.0834, 0.7356, 0.4293)],
		[30.389, Vector3(2.0834, 0.7356, 0.4293)]
	],
}


## A soil_state with `thickness` and one texture, SOC, theta, FC and WP for
## every layer.
func _soil(
	thickness: Array, texture: String, soc: float = 1.0, theta: float = 0.2, fc: float = 0.25
) -> Dictionary:
	var n := thickness.size()
	var fill := func(v: Variant) -> Array:
		var out: Array = []
		out.resize(n)
		out.fill(v)
		return out
	return {
		"layer_thickness_cm": thickness,
		"texture": fill.call(texture),
		"soc_pct": fill.call(soc),
		"water_theta": fill.call(theta),
		"field_capacity": fill.call(fc),
		"wilting_point": fill.call(0.12),
	}


func test_preset_hues_reproduce_their_cited_munsell_notations() -> void:
	# At the notation's own L*, hue_at() gives the renotation's colour back.
	for key: String in MUNSELL:
		var lch: Array = SoilFaceColour.PRESET_LCH[key]
		assert_eq(lch.size(), MUNSELL[key].size(), key)
		for i in range(lch.size()):
			var want: Array = MUNSELL[key][i]
			var got := SoilFaceColour.hue_at(want[0], lch[i])
			assert_almost_eq(got, want[1], Vector3.ONE * 0.005, "%s layer %d" % [key, i])
			assert_almost_eq(got.dot(SoilFaceColour.REC709), 1.0, 1e-5, "unit luminance")
	var nl: Array = SoilFaceColour.PRESET_LCH["clay_netherlands"]
	assert_eq(nl, SoilFaceColour.PRESET_LCH["clay_temperate"], "the same Dutch marine clay")


func test_a_lighter_layer_keeps_its_chroma_so_its_hue_is_paler() -> void:
	# Value comes from the cited mapping, hue and chroma from the notation: the
	# same CIELAB chroma at a higher L* is a less saturated chromaticity.
	var bt: Vector2 = SoilFaceColour.PRESET_LCH["sandy_subsaharan"][2]
	var at_4 := SoilFaceColour.hue_at(40.755, bt)
	var at_7 := SoilFaceColour.hue_at(70.0, bt)
	assert_lt(at_7.x, at_4.x, "less red")
	assert_gt(at_7.z, at_4.z, "less yellow-orange")


func test_lab_lightness_is_cie_15() -> void:
	assert_almost_eq(SoilFaceColour.lab_lightness(1.0), 100.0, 1e-4)
	assert_almost_eq(SoilFaceColour.lab_lightness(0.18419), 50.0, 1e-3)
	assert_almost_eq(SoilFaceColour.lab_lightness(0.0), 0.0, 1e-6)
	var knee := pow(SoilFaceColour.LAB_DELTA, 3.0)
	assert_almost_eq(
		SoilFaceColour.lab_lightness(knee * 0.999999),
		SoilFaceColour.lab_lightness(knee * 1.000001),
		1e-3,
		"continuous at the breakpoint"
	)


func test_layers_without_a_citation_keep_the_texture_hue() -> void:
	var y := 0.12
	assert_eq(SoilFaceColour.layer_hue("peat_cool_wet", 0, 1, y), SoilFaceColour.hue(1), "no entry")
	assert_eq(
		SoilFaceColour.layer_hue("sandy_temperate", 2, 0, y), SoilFaceColour.hue(0), "below the B"
	)
	var lch: Vector2 = SoilFaceColour.PRESET_LCH["sandy_temperate"][1]
	var want := SoilFaceColour.hue_at(SoilFaceColour.lab_lightness(y), lch)
	assert_eq(SoilFaceColour.layer_hue("sandy_temperate", 1, 0, y), want, "the B is cited")


func test_kenya_loam_takes_the_nitisol_hue_by_climate() -> void:
	var tile := {"soil_profile_key": "loam_temperate", "climate_key": "kenya_highlands"}
	assert_eq(SoilFaceColour.colour_key(tile), "loam_temperate@kenya_highlands")
	tile["climate_key"] = "netherlands_temperate"
	assert_eq(SoilFaceColour.colour_key(tile), "loam_temperate")
	tile = {"soil_profile_key": "clay_temperate", "climate_key": "kenya_highlands"}
	assert_eq(SoilFaceColour.colour_key(tile), "clay_temperate", "only Kenya's loam is keyed")
	assert_eq(SoilFaceColour.colour_key({}), "")


func test_a_face_gain_gives_the_layer_its_hue_at_its_lightness() -> void:
	var soil := _soil([25.0, 35.0, 40.0], "sand", 0.17, 0.06, 0.09)
	soil["wilting_point"] = [0.03, 0.03, 0.03]
	for i in range(3):
		var gain := SoilFaceColour.face_gain(soil, "sandy_subsaharan", i)
		var face_mean: Vector3 = (
			gain * SoilFaceColour.CROSS_MEAN_LINEAR[0] * SoilFaceColour.layer_scale(soil, i)
		)
		var y := SoilFaceColour.layer_y(soil, i)
		assert_almost_eq(face_mean.dot(SoilFaceColour.REC709), y, 1e-4, "layer %d keeps Y" % i)
		var want := SoilFaceColour.layer_hue("sandy_subsaharan", i, 0, y) * y
		assert_almost_eq(face_mean, want, Vector3.ONE * 1e-4, "layer %d: its hue" % i)


func test_the_top_is_the_faces_top_band() -> void:
	# One colour (#680): the top's mean albedo, grain included, is the face's
	# top-band mean, and the top texture only carries the detail.
	for key: String in ["sandy_temperate", "loam_temperate", "clay_temperate"]:
		var texture := "sand" if key.begins_with("sandy") else key.get_slice("_", 0)
		var soil := _soil([25.0, 35.0, 40.0], texture, 1.2, 0.2, 0.25)
		var col := SoilFaceColour.column(texture)
		var albedo := SoilFaceColour.surface_albedo(soil, key)
		var face: Vector3 = (
			SoilFaceColour.face_gain(soil, key, 0)
			* SoilFaceColour.CROSS_MEAN_LINEAR[col]
			* SoilFaceColour.layer_scale(soil, 0)
		)
		assert_almost_eq(albedo, face, Vector3.ONE * 1e-5, key)
		var top: Vector3 = (
			SoilFaceColour.top_gain(albedo, col)
			* SoilFaceColour.TOP_MEAN_LINEAR[col]
			* SoilFaceColour.TOP_GRAIN_MEAN
		)
		assert_almost_eq(top, albedo, Vector3.ONE * 1e-5, "%s top mean" % key)


func test_texture_means_are_the_pngs() -> void:
	# TOP_MEAN_LINEAR, CROSS_MEAN_LINEAR and CROSS_MEAN_Y, re-measured: every
	# 7th pixel each way, sRGB decoded (IEC 61966-2-1).
	var tops: Array[String] = [
		FarmLayout.SOIL_TEXTURES["sandy"]["albedo"],
		FarmLayout.SOIL_TEXTURES["organic"]["albedo"],
		FarmLayout.SOIL_TEXTURES["clay"]["albedo"],
	]
	for col in range(3):
		var top := _linear_mean(tops[col])
		var cross := _linear_mean(SoilFaceColour.CROSS_TEXTURES[col])
		assert_almost_eq(top, SoilFaceColour.TOP_MEAN_LINEAR[col], Vector3.ONE * 0.004, tops[col])
		var want: Vector3 = SoilFaceColour.CROSS_MEAN_LINEAR[col]
		assert_almost_eq(cross, want, Vector3.ONE * 0.004, "cross %d" % col)
		assert_almost_eq(
			want.dot(SoilFaceColour.REC709), SoilFaceColour.CROSS_MEAN_Y[col], 0.002, "cross Y"
		)


func test_top_grain_mean_is_the_shaders() -> void:
	# soil_tile.gdshader's grain, fine grain and cracks, ported: their mean
	# product over the farm is TOP_GRAIN_MEAN.
	var rng := RandomNumberGenerator.new()
	rng.seed = 680
	var total := 0.0
	var n := 4000
	for i in range(n):
		var wp := Vector2(rng.randf_range(-3.0, 3.0), rng.randf_range(-3.0, 3.0))
		var fine := _fbm(wp * 80.0)
		var coarse := _fbm(wp * 25.0)
		var cracks := smoothstep(0.48, 0.50, _fbm(wp * 40.0 + Vector2(3.7, 1.2)))
		total += (0.85 + coarse * 0.3) * (0.9 + (fine - 0.5) * 0.25) * (1.0 - cracks * 0.3)
	assert_almost_eq(total / n, SoilFaceColour.TOP_GRAIN_MEAN, 0.01)


func test_saturation_is_theta_over_porosity() -> void:
	var soil := _soil([25.0], "loam", 1.0, 0.2)
	assert_eq(SoilFaceColour.saturation(soil), 0.0, "no porosity, no gloss")
	soil["porosity"] = [0.45]
	assert_almost_eq(SoilFaceColour.saturation(soil), 0.2 / 0.45, 1e-6)
	soil["water_theta"] = [0.5]
	assert_eq(SoilFaceColour.saturation(soil), 1.0, "clamped")


func _linear_mean(path: String) -> Vector3:
	var img := Image.load_from_file(ProjectSettings.globalize_path(path))
	img.convert(Image.FORMAT_RGB8)
	var sum := Vector3.ZERO
	var n := 0
	for y in range(0, img.get_height(), 7):
		for x in range(0, img.get_width(), 7):
			var c := img.get_pixel(x, y).srgb_to_linear()
			sum += Vector3(c.r, c.g, c.b)
			n += 1
	return sum / n


func _hash(p: Vector2) -> float:
	var v := sin(p.dot(Vector2(127.1, 311.7))) * 43758.5453
	return v - floorf(v)


func _value_noise(p: Vector2) -> float:
	var i := p.floor()
	var f := p - i
	f = f * f * (Vector2(3.0, 3.0) - 2.0 * f)
	var a := _hash(i)
	var b := _hash(i + Vector2(1.0, 0.0))
	var c := _hash(i + Vector2(0.0, 1.0))
	var d := _hash(i + Vector2(1.0, 1.0))
	return lerpf(lerpf(a, b, f.x), lerpf(c, d, f.x), f.y)


func _fbm(p: Vector2) -> float:
	var v := 0.0
	var a := 0.5
	for i in range(4):
		v += a * _value_noise(p)
		p *= 2.1
		a *= 0.5
	return v
