extends GutTest
## Shading of the crop and soil shaders (#637). Colours are authored in sRGB
## and must reach the lighting maths as linear light: colour uniforms are set
## from a Color, which the engine converts (a Vector3 goes in unchanged), and
## colour literals and vertex colours go through SRGB_TO_LINEAR. Two-sided
## surfaces leave the back-face normal to the engine.

const CR = preload("res://scripts/crop_renderer_3d.gd")

const LEAF_SHADER := "res://shaders/crop_leaf.gdshader"
const ORGAN_SHADER := "res://shaders/crop_organ.gdshader"
const SOIL_SHADER := "res://shaders/soil_tile.gdshader"
const SRGB_INCLUDE := "res://shaders/srgb.gdshaderinc"


func test_colour_uniforms_are_set_as_colors() -> void:
	var leaf := CR.create_leaf_material("maize", 0.0, {})
	var stem := CR.create_stem_material(0.3)
	var organ := CR.create_organ_material(Color(0.8, 0.7, 0.4))
	assert_eq(typeof(leaf.get_shader_parameter("base_color")), TYPE_COLOR, "Leaf base colour")
	assert_eq(typeof(stem.get_shader_parameter("stem_color")), TYPE_COLOR, "Stem colour")
	assert_eq(typeof(organ.get_shader_parameter("albedo")), TYPE_COLOR, "Organ albedo")


func test_leaf_base_colour_is_the_authored_crop_colour() -> void:
	var leaf := CR.create_leaf_material("sorghum", 0.0, {})
	var base: Color = leaf.get_shader_parameter("base_color")
	assert_true(base.is_equal_approx(CR.LEAF_BASE_COLOR["sorghum"]), "sRGB value handed over as is")


func test_leaf_colour_constants_are_converted_to_linear() -> void:
	var text: String = _source(LEAF_SHADER)
	assert_string_contains(text, '#include "%s"' % SRGB_INCLUDE)
	var consts := RegEx.create_from_string("(?m)^const vec3 (\\w+) = (.*);")
	var found: Array[RegExMatch] = consts.search_all(text)
	assert_gt(found.size(), 10, "Senescence and stress colour targets are declared")
	for m: RegExMatch in found:
		assert_true(
			m.get_string(2).begins_with("SRGB_TO_LINEAR(vec3("),
			"%s is converted from sRGB" % m.get_string(1)
		)


func test_leaf_sheen_is_specular_not_albedo() -> void:
	var text: String = _source(LEAF_SHADER)
	assert_false(text.contains("color += vec3(sheen)"), "Sheen no longer lightens the albedo")
	assert_string_contains(text, "SPECULAR = 0.5;")
	assert_string_contains(text, "ROUGHNESS = mix(0.5, 0.8, effective_sen);")


func test_stress_strength_goes_through_one_response_curve() -> void:
	# #641: every overlay reads its strength through the same curve, so 0.6
	# is a clear difference on screen; zero stays zero.
	var text: String = _source(LEAF_SHADER)
	assert_string_contains(text, "const float STRESS_CURVE = 0.5;")
	for k: String in ["water", "n", "p", "fe", "zn", "frost", "heat"]:
		assert_string_contains(text, "float s_%s = pow(stress_%s, STRESS_CURVE);" % [k, k])
		assert_false(
			text.contains("= stress_%s *" % k), "stress_%s is only read through its curve" % k
		)


func test_sulfur_and_manganese_overlays() -> void:
	# #669: both read their strength through the #641 curve and weigh young
	# leaves first (Marschner 2012, ch. 6 and 7); S takes N's chlorosis colour,
	# Mn Fe's vein mask towards its own, duller colour.
	var text: String = _source(LEAF_SHADER)
	for k: String in ["s", "mn"]:
		assert_string_contains(text, "uniform float stress_%s : hint_range(0.0, 1.0) = 0.0;" % k)
		assert_string_contains(text, "float s_%s = pow(stress_%s, STRESS_CURVE);" % [k, k])
		assert_false(text.contains("= stress_%s *" % k), "stress_%s only through its curve" % k)
	assert_string_contains(text, "float s_f = s_s * (0.4 + young_leaf * 0.6);")
	assert_string_contains(text, "color = mix(color, N_DEFICIENCY, s_f);")
	assert_string_contains(text, "vec3 mn_color = mix(MN_CHLOROSIS, FE_VEIN_COLOR, is_vein);")
	assert_string_contains(text, "float mn_f = s_mn * (0.4 + young_leaf * 0.6);")
	assert_string_contains(text, "Hawkesford et al. 2012")
	assert_string_contains(text, "Broadley et al. 2012")
	# Order: S after N, Mn after Fe.
	assert_lt(text.find("N_DEFICIENCY, n_f"), text.find("N_DEFICIENCY, s_f"))
	assert_lt(text.find("fe_color, fe_f"), text.find("mn_color, mn_f"))


func test_mn_chlorosis_is_duller_than_iron() -> void:
	var text: String = _source(LEAF_SHADER)
	var fe := _srgb_const(text, "FE_CHLOROSIS")
	var mn := _srgb_const(text, "MN_CHLOROSIS")
	assert_lt(mn.s, fe.s, "less saturated")
	assert_lt(mn.v, fe.v, "darker")


func test_leaf_material_carries_sulfur_manganese_and_todays_ks() -> void:
	var stresses := StressUtils.parse_stress_data(
		{"water_ks": 0.3, "water_stress": 1.0, "s_stress": 0.4, "mn_stress": 0.2}
	)
	var leaf := CR.create_leaf_material("maize", 0.0, stresses)
	assert_almost_eq(float(leaf.get_shader_parameter("stress_s")), 0.4, 0.001)
	assert_almost_eq(float(leaf.get_shader_parameter("stress_mn")), 0.2, 0.001)
	# The drought tint and droop follow Ks (#669), not the growth factor.
	assert_almost_eq(float(leaf.get_shader_parameter("stress_water")), 0.7, 0.001)
	assert_almost_eq(CR.stress_droop_bonus(stresses), 0.42, 0.001, "0.7 x 0.6")


func _srgb_const(text: String, name: String) -> Color:
	var re := RegEx.create_from_string(
		"const vec3 %s = SRGB_TO_LINEAR\\(vec3\\(([\\d.]+), ([\\d.]+), ([\\d.]+)\\)\\);" % name
	)
	var m := re.search(text)
	assert_not_null(m, name)
	return Color(float(m.get_string(1)), float(m.get_string(2)), float(m.get_string(3)))


func test_heat_scorch_covers_tip_and_margin() -> void:
	var text: String = _source(LEAF_SHADER)
	assert_string_contains(text, "max(smoothstep(0.4, 0.85, UV.x), 0.8 * edge)")


func test_leaf_midrib_brightens_multiplicatively() -> void:
	var text: String = _source(LEAF_SHADER)
	assert_string_contains(text, "color = mix(color, color * 1.3, rib * midrib * 0.8);")
	assert_false(text.contains("color * 1.3 +"), "No fixed amount added along the rib")


func test_organ_vertex_colours_are_converted() -> void:
	var text: String = _source(ORGAN_SHADER)
	assert_string_contains(text, '#include "%s"' % SRGB_INCLUDE)
	assert_string_contains(text, "ALBEDO = albedo * SRGB_TO_LINEAR(COLOR.rgb);")


func test_soil_selection_colour_is_converted() -> void:
	var text: String = _source(SOIL_SHADER)
	assert_string_contains(text, '#include "%s"' % SRGB_INCLUDE)
	assert_string_contains(text, "vec3 sel_color = SRGB_TO_LINEAR(vec3(1.0, 0.85, 0.3));")


func test_srgb_macro_is_the_iec_curve() -> void:
	# IEC 61966-2-1: linear segment below 0.04045, slope 1/12.92; power 2.4
	# with offset 0.055 above it.
	var text: String = _source(SRGB_INCLUDE)
	assert_string_contains(text, "#define SRGB_TO_LINEAR(c)")
	for term: String in ["0.055", "1.055", "2.4", "12.92", "0.04045"]:
		assert_string_contains(text, term)


func _source(path: String) -> String:
	var text: String = FileAccess.get_file_as_string(path)
	assert_false(text.is_empty(), path + " is readable")
	return text


func test_two_sided_shaders_do_not_flip_the_normal_again() -> void:
	# With cull_disabled the engine turns NORMAL towards the viewer on a back
	# face before fragment() runs; a second flip shades that face from behind.
	for path: String in [LEAF_SHADER, ORGAN_SHADER]:
		var text: String = _source(path)
		assert_string_contains(text, "render_mode cull_disabled")
		assert_false(text.contains("NORMAL = -NORMAL"), path + " leaves NORMAL to the engine")
