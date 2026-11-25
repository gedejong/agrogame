extends GutTest
## SoilFaceColour (#646 criteria 2 and 3): the soil faces' lightness from
## SOC, texture and theta (FAO 2006 Tables 46 and 57, ASTM D1535), and the
## root density with depth (the engine's exponential kernel).


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


## Root density summed per layer of `thickness`, as fractions of the total.
func _layer_fractions(thickness: Array, root_cm: float, section_cm: float) -> Array[float]:
	var cells := SoilFaceColour.samples(_soil(thickness, "loam"), root_cm, section_cm)
	var sums: Array[float] = []
	sums.resize(thickness.size())
	sums.fill(0.0)
	var total := 0.0
	for p in range(cells.size()):
		var z := (p + 0.5) / SoilFaceColour.SAMPLES_PER_CM
		var bottom := 0.0
		for i in range(thickness.size()):
			bottom += thickness[i]
			if z <= bottom or i == thickness.size() - 1:
				sums[i] += cells[p].g
				break
		total += cells[p].g
	for i in range(sums.size()):
		sums[i] /= total
	return sums


func test_luminance_is_astm_d1535() -> void:
	assert_almost_eq(SoilFaceColour.luminance(3.0), 6.39, 0.01)
	assert_almost_eq(SoilFaceColour.luminance(5.0), 19.27, 0.01)
	assert_almost_eq(SoilFaceColour.luminance(10.0), 100.0, 0.01)


func test_moist_value_from_table_46() -> void:
	assert_almost_eq(SoilFaceColour.moist_value(2.0, "loam"), 3.25, 0.01)
	assert_almost_eq(SoilFaceColour.moist_value(1.2, "sand"), 3.47, 0.01)
	assert_almost_eq(SoilFaceColour.moist_value(3.0, "clay"), 3.21, 0.01)
	assert_almost_eq(SoilFaceColour.moist_value(0.3, "sand"), 4.75, 0.01)


func test_dry_value_from_table_46() -> void:
	assert_almost_eq(SoilFaceColour.dry_value(1.2, "sand"), 5.52, 0.01)
	assert_almost_eq(SoilFaceColour.dry_value(2.0, "loam"), 5.29, 0.01)


func test_textures_map_to_table_46_columns() -> void:
	var textures := ["sand", "sandy_loam", "loam", "peat", "clay_loam", "clay"]
	var got: Array = textures.map(func(t: String) -> int: return SoilFaceColour.column(t))
	assert_eq(got, [0, 1, 1, 1, 2, 2])


func test_values_never_rise_with_organic_matter() -> void:
	for texture: String in ["sand", "loam", "clay"]:
		var moist := INF
		var dry := INF
		var om := 0.05
		while om <= 40.0:
			var vm := SoilFaceColour.moist_value(om, texture)
			var vd := SoilFaceColour.dry_value(om, texture)
			assert_true(vm <= moist + 1e-9 and vd <= dry + 1e-9, "%s at OM %.3f" % [texture, om])
			if om >= 0.3 and om <= 6.0:
				assert_between(vd - vm, 1.2, 2.4, "%s dry - moist at OM %.3f" % [texture, om])
			moist = vm
			dry = vd
			om *= 1.05


func test_dry_share_follows_table_57_in_pf() -> void:
	assert_eq(SoilFaceColour.dry_share(0.25, 0.25, 0.12), 0.0, "at FC")
	assert_eq(SoilFaceColour.dry_share(0.40, 0.25, 0.12), 0.0, "above FC")
	assert_almost_eq(SoilFaceColour.dry_share(0.12, 0.25, 0.12), 0.733, 0.001, "at WP")
	assert_almost_eq(SoilFaceColour.dry_share(0.0, 0.25, 0.12), 1.0, 1e-6, "oven-dry")


## Measured Netherlands topsoils on day 63 and day 64 (35 mm of rain), seed 42.
func test_netherlands_topsoils_darken_after_rain() -> void:
	var cases := [
		["sand", 0.692, 0.12, 0.05, 0.063, 0.115, 16.8, 9.2],
		["loam", 1.149, 0.25, 0.12, 0.167, 0.245, 13.1, 7.8],
		["clay", 1.723, 0.36, 0.20, 0.274, 0.332, 11.8, 8.7],
	]
	for c: Array in cases:
		var before := SoilFaceColour.reflectance(c[1], c[0], c[4], c[2], c[3])
		var after := SoilFaceColour.reflectance(c[1], c[0], c[5], c[2], c[3])
		assert_almost_eq(before, c[6], 0.2, "%s day 63" % c[0])
		assert_almost_eq(after, c[7], 0.2, "%s day 64" % c[0])


func test_layer_scale_is_reflectance_over_the_texture_mean() -> void:
	var soil := _soil([25.0], "sand", 0.692, 0.063, 0.12)
	soil["wilting_point"] = [0.05]
	var y := SoilFaceColour.reflectance(0.692, "sand", 0.063, 0.12, 0.05)
	assert_almost_eq(y, 16.8, 0.2)
	assert_almost_eq(SoilFaceColour.layer_scale(soil, 0), y / 100.0 / 0.462, 1e-6)


func test_root_density_is_the_engine_kernel() -> void:
	assert_eq(SoilFaceColour.root_density(0.0, 60.0), 1.0)
	assert_almost_eq(SoilFaceColour.root_density(30.0, 60.0), 0.368, 0.001)
	assert_eq(SoilFaceColour.root_density(60.5, 60.0), 0.0)
	assert_eq(SoilFaceColour.root_density(10.0, 0.0), 0.0)


func test_sampled_roots_reproduce_the_api_layer_fractions() -> void:
	var first := _layer_fractions([25.0, 35.0, 40.0], 63.5, 100.0)
	var second := _layer_fractions([30.0, 35.0, 40.0], 56.1, 105.0)
	for i in range(3):
		assert_almost_eq(first[i], [0.63, 0.35, 0.02][i], 0.02, "D 63.5, layer %d" % i)
		assert_almost_eq(second[i], [0.76, 0.24, 0.00][i], 0.02, "D 56.1, layer %d" % i)


func test_roots_end_at_the_front_and_never_below_the_section() -> void:
	for root_cm: float in [60.0, 100.0]:
		var cells := SoilFaceColour.samples(_soil([25.0, 35.0, 40.0], "loam"), root_cm, 100.0)
		assert_eq(cells.size(), 200, "one sample per 0.5 cm, none below the section")
		var deepest := -1.0
		for p in range(cells.size()):
			if cells[p].g > 0.0:
				deepest = (p + 0.5) / SoilFaceColour.SAMPLES_PER_CM
		assert_almost_eq(deepest, root_cm, 1.0, "front at %.0f cm" % root_cm)


func test_samples_extend_the_bottom_layer_and_mark_seams() -> void:
	var soil := _soil([25.0, 35.0, 40.0], "loam")
	soil["water_theta"] = [0.25, 0.20, 0.13]
	var cells := SoilFaceColour.samples(soil, 0.0, 105.0)
	var at := func(z: float) -> Color: return cells[floori(z * SoilFaceColour.SAMPLES_PER_CM)]
	var dark := 1.0 - SoilFaceColour.SEAM_DARKEN
	assert_almost_eq(at.call(10.0).r, SoilFaceColour.layer_scale(soil, 0), 1e-5, "topsoil")
	assert_almost_eq(at.call(25.2).r, SoilFaceColour.layer_scale(soil, 1) * dark, 1e-5, "seam 25")
	assert_almost_eq(at.call(60.2).r, SoilFaceColour.layer_scale(soil, 2) * dark, 1e-5, "seam 60")
	assert_almost_eq(at.call(101.0).r, SoilFaceColour.layer_scale(soil, 2), 1e-5, "extended")
	assert_almost_eq(at.call(104.6).r, SoilFaceColour.layer_scale(soil, 2) * dark, 1e-5, "bottom")
	assert_eq(at.call(50.0).b, 0.5, "loam column")


func test_has_profile_needs_every_key_at_one_length() -> void:
	var soil := _soil([25.0, 35.0, 40.0], "loam")
	assert_true(SoilFaceColour.has_profile(soil))
	assert_eq(SoilFaceColour.profile_depth_cm(soil), 100.0)
	soil["soc_pct"] = [1.0]
	assert_false(SoilFaceColour.has_profile(soil), "short soc_pct")
	assert_false(SoilFaceColour.has_profile({"water_theta": [0.2]}), "no layout")
